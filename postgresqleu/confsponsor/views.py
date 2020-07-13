from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, Http404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.db import transaction, connection
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone

from datetime import timedelta
import io
import random
from collections import OrderedDict
from decimal import Decimal

from postgresqleu.auth import user_search, user_import

from postgresqleu.confreg.models import Conference, PrepaidVoucher, PrepaidBatch, DiscountCode
from postgresqleu.confreg.util import get_authenticated_conference, get_conference_or_404
from postgresqleu.confreg.jinjafunc import render_sandboxed_template
from postgresqleu.confreg.util import send_conference_mail, send_conference_notification
from postgresqleu.confreg.twitter import post_conference_social
from postgresqleu.util.storage import InlineEncodedStorage
from postgresqleu.util.decorators import superuser_required
from postgresqleu.util.request import get_int_or_error
from postgresqleu.util.time import today_global
from postgresqleu.invoices.util import InvoiceWrapper, InvoiceManager

from .models import Sponsor, SponsorshipLevel, SponsorshipBenefit
from .models import SponsorClaimedBenefit, SponsorMail, SponsorshipContract
from .models import PurchasedVoucher
from .models import ShipmentAddress, Shipment
from .forms import SponsorSignupForm, SponsorSendEmailForm, SponsorDetailsForm
from .forms import PurchaseVouchersForm, PurchaseDiscountForm
from .forms import SponsorShipmentForm, ShipmentReceiverForm
from .forms import SponsorRefundForm, SponsorReissueForm

from .benefits import get_benefit_class
from .invoicehandler import create_sponsor_invoice, confirm_sponsor
from .invoicehandler import get_sponsor_invoice_address, get_sponsor_invoice_rows
from .invoicehandler import create_voucher_invoice
from .vatutil import validate_eu_vat_number
from .util import send_conference_sponsor_notification


@login_required
def sponsor_dashboard(request):
    # We define "past sponsors" as those older than a month - because we have to pick something.
    currentsponsors = Sponsor.objects.filter(managers=request.user, conference__enddate__gte=today_global() - timedelta(days=31)).order_by('conference__startdate')
    pastsponsors = Sponsor.objects.filter(managers=request.user, conference__enddate__lt=today_global() - timedelta(days=31)).order_by('conference__startdate')
    conferences = Conference.objects.filter(callforsponsorsopen=True, startdate__gt=today_global()).order_by('startdate')

    return render(request, 'confsponsor/dashboard.html', {
        "currentsponsors": currentsponsors,
        "pastsponsors": pastsponsors,
        "conferences": conferences,
        })


def _get_sponsor_and_admin(sponsorid, request, onlyconfirmed=True):
    if not onlyconfirmed:
        sponsor = get_object_or_404(Sponsor, id=sponsorid)
    else:
        sponsor = get_object_or_404(Sponsor, id=sponsorid, confirmed=True)
    if not sponsor.managers.filter(pk=request.user.id).exists():
        if request.user.is_superuser:
            return sponsor, True
        if not sponsor.conference.administrators.filter(pk=request.user.id).exists() and not sponsor.conference.series.administrators.filter(pk=request.user.id).exists():
            raise PermissionDenied("Access denied")
        # Else user is admin of conference or conference series
        return sponsor, True
    else:
        # End user is directly a manager of this sponsorship
        return sponsor, False


@login_required
def sponsor_conference(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request, False)

    unclaimedbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=False).exclude(sponsorclaimedbenefit__sponsor=sponsor)
    claimedbenefits = SponsorClaimedBenefit.objects.filter(sponsor=sponsor).order_by('confirmed', 'benefit__sortkey')
    noclaimbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=True)
    mails = SponsorMail.objects.filter(conference=sponsor.conference).filter(Q(levels=sponsor.level) | Q(sponsors=sponsor))
    vouchers = PrepaidVoucher.objects.filter(batch__sponsor=sponsor)
    pendingvouchers = PurchasedVoucher.objects.filter(sponsor=sponsor, batch__isnull=True)
    discountcodes = DiscountCode.objects.filter(sponsor=sponsor)

    if request.method == 'POST':
        detailsform = SponsorDetailsForm(instance=sponsor, data=request.POST)
        if detailsform.is_valid():
            detailsform.save()
            return HttpResponseRedirect(".")
    else:
        detailsform = SponsorDetailsForm(instance=sponsor)

    for b in claimedbenefits:
        if b.benefit.benefit_class and not b.declined:
            b.claimhtml = get_benefit_class(b.benefit.benefit_class)(sponsor.level, b.benefit.class_parameters).render_claimdata(b)

    addresses = ShipmentAddress.objects.filter(conference=sponsor.conference, available_to=sponsor.level, active=True)
    shipments = Shipment.objects.filter(sponsor=sponsor)

    return render(request, 'confsponsor/sponsor.html', {
        'conference': sponsor.conference,
        'sponsor': sponsor,
        'unclaimedbenefits': unclaimedbenefits,
        'claimedbenefits': claimedbenefits,
        'noclaimbenefits': noclaimbenefits,
        'mails': mails,
        'vouchers': vouchers,
        'pendingvouchers': pendingvouchers,
        'discountcodes': discountcodes,
        'is_admin': is_admin,
        'detailsform': detailsform,
        'addresses': addresses,
        'shipments': shipments,
        })


@login_required
def sponsor_manager_delete(request, sponsorid):
    if 'id' not in request.POST:
        raise Http404("No id")

    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
    user = get_object_or_404(User, id=get_int_or_error(request.POST, 'id'))

    if user == request.user:
        messages.warning(request, "Can't delete yourself! Have one of your colleagues do it...")
        return HttpResponseRedirect('../../')

    sponsor.managers.remove(user)
    sponsor.save()
    messages.info(request, "User %s removed as manager." % user.username)
    return HttpResponseRedirect('../../')


@login_required
@transaction.atomic
def sponsor_manager_add(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)

    if not request.POST.get('email', ''):
        messages.warning(request, "Email not specified")
        return HttpResponseRedirect('../../')
    try:
        user = User.objects.get(email=request.POST['email'].lower())
        sponsor.managers.add(user)
        sponsor.save()
        messages.info(request, "User %s added as manager." % user.username)
        return HttpResponseRedirect('../../')
    except User.DoesNotExist:
        # Try an upstream search if the user is not here
        users = user_search(request.POST['email'].lower())
        if len(users) == 1 and users[0]['e'] == request.POST['email'].lower():
            try:
                user_import(users[0]['u'])
                try:
                    u = User.objects.get(username=users[0]['u'])
                    sponsor.managers.add(u)
                    sponsor.save()
                    messages.info(request, "User with email %s imported as user %s." % (u.email, u.username))
                    messages.info(request, "User %s added as manager." % u.username)
                except User.DoesNotExist:
                    messages.warning(request, "Failed to re-find user %s after import" % users[0]['u'])
            except Exception as e:
                messages.warning(request, "Failed to import user with email %s (userid %s): %s" % (users[0]['e'], users[0]['u'], e))
        else:
            messages.warning(request, "Could not find user with email address %s" % request.POST['email'].lower())
        return HttpResponseRedirect('../../')


@login_required
def sponsor_view_mail(request, sponsorid, mailid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)

    mail = get_object_or_404(SponsorMail, Q(levels=sponsor.level) | Q(sponsors=sponsor), conference=sponsor.conference, id=mailid)

    return render(request, 'confsponsor/sent_mail_user.html', {
        'conference': sponsor.conference,
        'mail': mail,
        })


@login_required
@transaction.atomic
def sponsor_purchase_voucher(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
    conference = sponsor.conference

    if request.method == 'POST':
        form = PurchaseVouchersForm(conference, data=request.POST)
        if form.is_valid():
            # Create an invoice (backwards order?)
            rt = form.cleaned_data['regtype']
            invoice = create_voucher_invoice(sponsor.conference,
                                             sponsor.invoiceaddr,
                                             request.user,
                                             rt,
                                             int(form.cleaned_data['num']))

            # Create a purchase order
            pv = PurchasedVoucher(conference=sponsor.conference,
                                  sponsor=sponsor,
                                  user=request.user,
                                  regtype=form.cleaned_data['regtype'],
                                  num=int(form.cleaned_data['num']),
                                  invoice=invoice)
            pv.save()
            invoice.processorid = pv.pk
            invoice.save()

            wrapper = InvoiceWrapper(invoice)
            wrapper.email_invoice()

            return HttpResponseRedirect('/invoices/{0}/'.format(invoice.pk))
    else:
        form = PurchaseVouchersForm(conference)

    return render(request, 'confsponsor/purchasevouchers.html', {
        'conference': conference,
        'user_name': request.user.first_name + ' ' + request.user.last_name,
        'sponsor': sponsor,
        'form': form,
        'savebutton': 'Purchase!',
        'cancelurl': '../../',
        })


@login_required
@transaction.atomic
def sponsor_purchase_discount(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
    conference = sponsor.conference

    if request.method == 'POST':
        if 'confirm' in request.POST:
            form = PurchaseDiscountForm(conference, showconfirm=True, data=request.POST)
        else:
            form = PurchaseDiscountForm(conference, data=request.POST)
        if form.is_valid():
            if 'confirm' not in form.cleaned_data:
                form = PurchaseDiscountForm(conference, showconfirm=True, data=request.POST)
            else:
                # Generate the code. We can't generate the invoice at this point, as it
                # will be depending on the discount code.
                code = DiscountCode(conference=conference,
                                    code=form.cleaned_data['code'],
                                    discountamount=form.cleaned_data['amount'] or 0,
                                    discountpercentage=form.cleaned_data['percent'] or 0,
                                    regonly=True,
                                    validuntil=form.cleaned_data['expires'],
                                    maxuses=form.cleaned_data['maxuses'],
                                    sponsor=sponsor,
                                    sponsor_rep=request.user,
                                    is_invoiced=False
                                    )
                code.save()
                # ManyToMany requires us to save before we can add the required options
                for o in form.cleaned_data['requiredoptions']:
                    code.requiresoption.add(o)
                code.save()

                messages.info(request, 'Discount code {0} has been created.'.format(code.code))
                return HttpResponseRedirect('../../')
    else:
        form = PurchaseDiscountForm(conference)

    return render(request, 'confsponsor/purchasediscount.html', {
        'conference': conference,
        'user_name': request.user.first_name + ' ' + request.user.last_name,
        'sponsor': sponsor,
        'form': form,
        'savebutton': 'Purchase!',
        'cancelurl': '../../',
        })


@login_required
def sponsor_signup_dashboard(request, confurlname):
    conference = get_conference_or_404(confurlname)
    if not conference.callforsponsorsopen:
        # This one is not open. But if we're an admin, we may bypass
        get_authenticated_conference(request, confurlname)

    current_signups = Sponsor.objects.filter(managers=request.user, conference=conference)
    levels = SponsorshipLevel.objects.filter(conference=conference, public=True)

    return render(request, 'confsponsor/signup.html', {
        'conference': conference,
        'levels': levels,
        'current': current_signups,
        })


@login_required
@transaction.atomic
def sponsor_signup(request, confurlname, levelurlname):
    conference = get_conference_or_404(confurlname)
    if not conference.callforsponsorsopen:
        # This one is not open. But if we're an admin, we may bypass
        get_authenticated_conference(request, confurlname)

    level = get_object_or_404(SponsorshipLevel, conference=conference, urlname=levelurlname, available=True, public=True)
    if not level.can_signup:
        messages.error(request, "This level is not currently available for signup")
        return HttpResponseRedirect("../")

    user_name = request.user.first_name + ' ' + request.user.last_name

    if request.method == 'POST':
        form = SponsorSignupForm(conference, data=request.POST)
        if not request.POST.get('confirm', '0') == '1':
            if form.is_valid():
                # Confirm not set, but form valid: show the address verification.
                return render(request, 'confsponsor/signupform.html', {
                    'user_name': user_name,
                    'conference': conference,
                    'level': level,
                    'form': form,
                    'previewaddr': get_sponsor_invoice_address(form.cleaned_data['name'],
                                                               form.cleaned_data['address'],
                                                               settings.EU_VAT and form.cleaned_data['vatnumber'] or None)
                })
                # Else fall through to re-render the full form
            # If form not valid, fall through to error below
        elif form.is_valid():
            # Confirm is set, but if the Continue editing button is selected we should go back
            # to just rendering the normal form. Otherwise, go ahead and create the record.
            if request.POST.get('submit', '') != 'Continue editing':
                twname = form.cleaned_data.get('twittername', '')
                if twname and twname[0] != '@':
                    twname = '@{0}'.format(twname)
                sponsor = Sponsor(conference=conference,
                                  signupat=timezone.now(),
                                  name=form.cleaned_data['name'],
                                  displayname=form.cleaned_data['displayname'],
                                  url=form.cleaned_data['url'],
                                  level=level,
                                  twittername=twname,
                                  invoiceaddr=form.cleaned_data['address'])
                if settings.EU_VAT:
                    sponsor.vatstatus = int(form.cleaned_data['vatstatus'])
                    sponsor.vatnumber = form.cleaned_data['vatnumber']
                sponsor.save()
                sponsor.managers.add(request.user)
                sponsor.save()

                mailstr = "Sponsor %s signed up for conference\n%s at level %s.\n\n" % (sponsor.name, conference, level.levelname)

                if level.instantbuy:
                    mailstr += "Level does not require a signed contract. Verify the details and approve\nthe sponsorship using:\n\n{0}/events/sponsor/admin/{1}/{2}/".format(
                        settings.SITEBASE, conference.urlname, sponsor.id)
                else:
                    mailstr += "No invoice has been generated as for this level\na signed contract is required first. The sponsor\nhas been instructed to sign and send the contract."

                send_conference_notification(
                    conference,
                    "Sponsor %s signed up for %s" % (sponsor.name, conference),
                    mailstr,
                )
                # Redirect back to edit the actual sponsorship entry
                return HttpResponseRedirect('/events/sponsor/%s/' % sponsor.id)
    else:
        form = SponsorSignupForm(conference)

    return render(request, 'confsponsor/signupform.html', {
        'user_name': user_name,
        'conference': conference,
        'level': level,
        'form': form,
        })


@login_required
@transaction.atomic
def sponsor_claim_benefit(request, sponsorid, benefitid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
    benefit = get_object_or_404(SponsorshipBenefit, id=benefitid, level=sponsor.level)

    if not sponsor.confirmed:
        # Should not happen
        return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)

    if not benefit.benefit_class:
        messages.warning(request, "Benefit does not require claiming")
        return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)

    # Let's see if it's already claimed
    if SponsorClaimedBenefit.objects.filter(sponsor=sponsor, benefit=benefit).exists():
        messages.warning(request, "Benefit has already been claimed")
        return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)

    # Find the actual type of benefit this is, so we know what to do about it
    benefitclass = get_benefit_class(benefit.benefit_class)(benefit.level, benefit.class_parameters)

    formclass = benefitclass.generate_form()

    # Are we trying to process incoming data yet?
    if request.method == 'POST':
        form = formclass(benefit, request.POST, request.FILES)
        if form.is_valid():
            # Always create a new claim here - we might support editing an existing one
            # sometime in the future, but not yet...
            claim = SponsorClaimedBenefit(sponsor=sponsor, benefit=benefit, claimedat=timezone.now(), claimedby=request.user)
            claim.save()  # generate an id

            send_mail = benefitclass.save_form(form, claim, request)

            claim.save()  # Just in case the claimdata field was modified

            if send_mail:
                if claim.declined:
                    mailstr = "Sponsor %s for conference %s has declined benefit %s.\n" % (sponsor, sponsor.conference, benefit)
                elif claim.confirmed:
                    # Auto-confirmed, so nothing to do here
                    mailstr = "Sponsor %s for conference %s has claimed benefit %s.\n\nThis has been automatically processed, so there is nothing more to do.\n" % (sponsor, sponsor.conference, benefit)
                else:
                    mailstr = "Sponsor %s for conference %s has claimed benefit %s\n\nThis benefit requires confirmation (and possibly some\nmore actions before that). Please go to\n%s/events/sponsor/admin/%s/\nand approve as necessary!" % (
                        sponsor,
                        sponsor.conference,
                        benefit,
                        settings.SITEBASE,
                        sponsor.conference.urlname)
                send_conference_notification(
                    sponsor.conference,
                    "Sponsor %s %s sponsorship benefit %s" % (sponsor, claim.declined and 'declined' or 'claimed', benefit),
                    mailstr,
                )

            messages.info(request, "Benefit \"%s\" has been %s." % (benefit, claim.declined and 'declined' or 'claimed'))
            return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)
    else:
        form = formclass(benefit)

    return render(request, 'confsponsor/claim_form.html', {
        'conference': sponsor.conference,
        'sponsor': sponsor,
        'benefit': benefit,
        'form': form,
        'savebutton': 'Claim!',
        })


@login_required
def admin_shipment_new(request, confurlname):
    conference = get_authenticated_conference(request, confurlname)

    return _sender_shipment_new(request, conference, None)


@login_required
def sponsor_shipment_new(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)

    return _sender_shipment_new(request, sponsor.conference, sponsor)


@transaction.atomic
def _sender_shipment_new(request, conference, sponsor):
    if sponsor:
        addresses = ShipmentAddress.objects.filter(conference=conference, available_to=sponsor.level, active=True)
    else:
        addresses = ShipmentAddress.objects.filter(conference=conference, active=True)

    if request.method == 'POST':
        # Figure out which one it is for
        for a in addresses:
            if 'submit-{0}'.format(a.id) in request.POST:
                address = a
                break
        else:
            raise Http404()

        for x in range(1, 25):
            # Make 25 attempts to create a unique token :D
            shipment, created = Shipment.objects.get_or_create(conference=conference,
                                                               addresstoken=random.randint(10000, 99999),
                                                               defaults={
                                                                   'sponsor': sponsor,
                                                                   'address': address,
                                                                   'description': request.POST.get('description', ''),
                                                                   'sent_parcels': 0,
                                                                   'arrived_parcels': 0,
                                                               },
            )
            if created:
                shipment.save()

                sname = sponsor and 'Sponsor {0}'.format(sponsor) or 'Conference organizers'
                send_conference_sponsor_notification(
                    conference,
                    "{0} requested a new shipment".format(sname),
                    "New shipment with description '{0}' requested for destination\n{1}\nNot sent yet.".format(shipment.description, shipment.address.title),
                )

                return HttpResponseRedirect("../{0}/".format(shipment.addresstoken))

        raise Exception("Unable to generate a unique token!")

    return render(request, 'confsponsor/new_shipment_address.html', {
        'conference': conference,
        'sponsor': sponsor,
        'addresses': addresses,
    })


@login_required
def admin_shipment(request, confurlname, shipmentid):
    conference = get_authenticated_conference(request, confurlname)

    return _sender_shipment(request, conference, None, shipmentid)


@login_required
def sponsor_shipment(request, sponsorid, shipmentid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)

    return _sender_shipment(request, sponsor.conference, sponsor, shipmentid)


@transaction.atomic
def _sender_shipment(request, conference, sponsor, shipmentid):
    shipment = get_object_or_404(Shipment,
                                 conference=conference,
                                 sponsor=sponsor,
                                 addresstoken=shipmentid)

    if request.method == 'POST':
        if shipment.arrived_at:
            messages.error(request, "This shipment has arrived and can no longer be edited")
            return HttpResponseRedirect(".")

        if request.POST['submit'] == 'Delete':
            if shipment.sent_at:
                # Can only happen on concurrent edits, but still
                messages.error(request, "This shipment has been sent and can no longer be deleted")
                return HttpResponseRedirect(".")

            sname = sponsor and 'Sponsor {0}'.format(sponsor) or 'Conference organizers'
            send_conference_sponsor_notification(
                conference,
                "{0} deleted a shipment".format(sname),
                "Shipment with id {0} and description '{1}' was deleted.\nIt had not been marked as sent yet.\n".format(shipment.addresstoken, shipment.description),
            )
            shipment.delete()
            messages.info(request, "Shipment {0} deleted".format(shipmentid))
            return HttpResponseRedirect("../../#shipment")

        form = SponsorShipmentForm(instance=shipment, data=request.POST)
        oldsent = shipment.sent_at
        if form.is_valid():
            # Save it, and also notify sponsor management that someting
            # is going on.
            if oldsent is None and form.cleaned_data['sent_at'] is not None:
                subject = "marked a shipment as sent"
            elif oldsent is not None and form.cleaned_data['sent_at'] is None:
                subject = "*unmarked* a previously sent shipment!"
            elif form.cleaned_data['sent_at'] is not None:
                subject = "updated a sent shipment"
            else:
                subject = None

            form.save()

            if subject:
                mailstr = "Shipment id: {0}\nDescription: {1}\nSent date:   {2}\nParcels:     {3}\nShipper:     {4}\nTracking nr: {5}\nTracking link: {6}\n".format(
                    form.instance.addresstoken,
                    form.instance.description,
                    form.instance.sent_at,
                    form.instance.sent_parcels,
                    form.instance.shippingcompany,
                    form.instance.trackingnumber,
                    form.instance.trackinglink,
                )
                sname = sponsor and 'Sponsor {0}'.format(sponsor) or 'Conference organizers'
                send_conference_sponsor_notification(
                    conference,
                    "{0} {1}".format(sname, subject),
                    mailstr,
                )
            return HttpResponseRedirect("../../#shipment")
    else:
        form = SponsorShipmentForm(instance=shipment)

    if shipment.sent_at or shipment.arrived_at:
        extrabutton = None
    else:
        extrabutton = 'Delete'

    return render(request, 'confsponsor/sponsor_shipment.html', {
        'conference': conference,
        'sponsor': sponsor,
        'shipment': shipment,
        'form': form,
        'cancelurl': '../../#shipment',
        'extrasubmitbutton': extrabutton,
        'extrasubmitbuttontype': 'warning',
    })


# Token based view for receiving side (e.g. hotel or partner)
def sponsor_shipment_receiver(request, token):
    address = get_object_or_404(ShipmentAddress, token=token)

    shipments = Shipment.objects.filter(address=address).order_by('addresstoken')

    return render(request, 'confsponsor/receiver_list.html', {
        'conference': address.conference,
        'address': address,
        'shipments': shipments,
    })


def _send_shipment_mail(shipment, subject, mailtemplate):
    if shipment.sponsor:
        for manager in shipment.sponsor.managers.all():
            send_conference_mail(shipment.conference,
                                 manager.email,
                                 subject,
                                 'confsponsor/mail/shipment_{0}.txt'.format(mailtemplate),
                                 {
                                     'shipment': shipment,
                                     'sponsor': shipment.sponsor,
                                 },
                                 sender=shipment.conference.sponsoraddr,
                                 bcc=shipment.conference.sponsoraddr,
                                 receivername='{0} {1}'.format(manager.first_name, manager.last_name),
                                 sendername=shipment.conference.conferencename)


@transaction.atomic
def sponsor_shipment_receiver_shipment(request, token, addresstoken):
    address = get_object_or_404(ShipmentAddress, token=token)
    shipment = get_object_or_404(Shipment, address=address, addresstoken=addresstoken)

    if request.method == 'POST':
        form = ShipmentReceiverForm(instance=shipment, data=request.POST)
        saved_arrived_parcels = shipment.arrived_parcels
        if form.is_valid():
            if request.POST['submit'] == 'Mark shipment as arrived':
                if shipment.arrived_at:
                    # Already done, so concurrent edit most likely. Just ignore.
                    messages.warning(request, "Shipment was already marked as arrived")
                else:
                    shipment.arrived_at = timezone.now()
                    shipment.arrived_parcels = request.POST['arrived_parcels']
                    shipment.save()
                    _send_shipment_mail(shipment,
                                        "Shipment to {0} marked as arrived".format(address.title),
                                        'arrived')
                    messages.info(request, "Shipment {0} marked as arrived".format(shipment.addresstoken))
            elif request.POST['submit'] == 'Mark as NOT arrived':
                if not shipment.arrived_at:
                    messages.warning(request, "Shipment is not marked as arrived!")
                else:
                    shipment.arrived_at = None
                    shipment.save()
                    _send_shipment_mail(shipment,
                                        "Shipment to {0} UNMARKED as arrived".format(address.title),
                                        'unmarked')
                    messages.info(request, "Shipment {0} marked as not arrived".format(shipment.addresstoken))
            elif request.POST['submit'] == "Change number of parcels":
                if saved_arrived_parcels != shipment.arrived_parcels:
                    shipment.save()
                    _send_shipment_mail(shipment,
                                        "Shipment to {0} updated number of parcels".format(address.title),
                                        'changed')
                    messages.info(request, "Number of parcels for shipment {0} changed".format(shipment.addresstoken))
            else:
                messages.error(request, "Invalid submit button pressed")
                return HttpResponseRedirect(".")
        return HttpResponseRedirect("../")
    else:
        form = ShipmentReceiverForm(instance=shipment)

    return render(request, 'confsponsor/receiver_form.html', {
        'conference': address.conference,
        'address': address,
        'shipment': shipment,
        'form': form,
        'cancelurl': '../',
        'savebutton': shipment.arrived_at and 'Change number of parcels' or 'Mark shipment as arrived',
        'extrasubmitbutton': shipment.arrived_at and 'Mark as NOT arrived' or None,
        'extrasubmitbuttontype': 'warning',
    })


@login_required
def sponsor_contract(request, contractid):
    # Our contracts are not secret, are they? Anybody can view them, we just require a login
    # to keep the load down and to make sure they are not spidered.

    contract = get_object_or_404(SponsorshipContract, pk=contractid)

    resp = HttpResponse(content_type='application/pdf')
    resp['Content-disposition'] = 'attachment; filename="%s.pdf"' % contract.contractname
    resp.write(bytes(contract.contractpdf))
    return resp


@login_required
def sponsor_admin_dashboard(request, confurlname):
    conference = get_authenticated_conference(request, confurlname)

    confirmed_sponsors = Sponsor.objects.select_related('invoice', 'level').filter(conference=conference, confirmed=True).order_by('-level__levelcost', 'confirmedat')
    unconfirmed_sponsors = Sponsor.objects.select_related('invoice', 'level').filter(conference=conference, confirmed=False).order_by('-level__levelcost', 'name')

    unconfirmed_benefits = SponsorClaimedBenefit.objects.filter(sponsor__conference=conference, confirmed=False).order_by('-sponsor__level__levelcost', 'sponsor', 'benefit__sortkey')

    mails = SponsorMail.objects.prefetch_related('levels', 'sponsors').filter(conference=conference)

    # Maybe we could do this with the ORM based on data we already have, but SQL is easier
    curs = connection.cursor()
    curs.execute("""
SELECT l.levelname, s.name, b.benefitname,
       CASE WHEN scb.declined='t' THEN 1 WHEN scb.confirmed='f' THEN 2 WHEN scb.confirmed='t' THEN 3 ELSE 0 END AS status
FROM confsponsor_sponsor s
INNER JOIN confsponsor_sponsorshiplevel l ON s.level_id=l.id
INNER JOIN confsponsor_sponsorshipbenefit b ON b.level_id=l.id
LEFT JOIN confsponsor_sponsorclaimedbenefit scb ON scb.sponsor_id=s.id AND scb.benefit_id=b.id
WHERE b.benefit_class IS NOT NULL AND s.confirmed AND s.conference_id=%(confid)s
ORDER BY l.levelcost DESC, l.levelname, s.name, b.sortkey, b.benefitname""", {'confid': conference.id})
    benefitmatrix = OrderedDict()
    currentlevel = None

    benefitcols = []
    currentmatrix = []
    lastsponsor = None
    currentsponsor = []
    firstsponsor = True
    for levelname, sponsor, benefitname, status in curs.fetchall():
        if lastsponsor != sponsor:
            # New sponsor...
            if currentsponsor:
                # We collected some data, so store it
                currentmatrix.append(currentsponsor)
                firstsponsor = False
            currentsponsor = [sponsor, ]
            lastsponsor = sponsor
        if levelname != currentlevel:
            if currentlevel:
                benefitmatrix[currentlevel] = {
                    'matrix': currentmatrix,
                    'cols': benefitcols,
                }
                benefitcols = []
                currentmatrix = []
                lastsponsor = sponsor
                currentsponsor = [sponsor, ]
                firstsponsor = True
            currentlevel = levelname
        if firstsponsor:
            benefitcols.append(benefitname)
        currentsponsor.append(status)
    currentmatrix.append(currentsponsor)
    benefitmatrix[currentlevel] = {
        'matrix': currentmatrix,
        'cols': benefitcols,
    }

    has_shipment_tracking = ShipmentAddress.objects.filter(conference=conference, active=True).exists()
    if has_shipment_tracking:
        shipments = Shipment.objects.select_related('address').filter(conference=conference).order_by('sponsor', 'addresstoken')
    else:
        shipments = None

    return render(request, 'confsponsor/admin_dashboard.html', {
        'conference': conference,
        'confirmed_sponsors': confirmed_sponsors,
        'unconfirmed_sponsors': unconfirmed_sponsors,
        'unconfirmed_benefits': unconfirmed_benefits,
        'mails': mails,
        'benefitcols': benefitcols,
        'benefitmatrix': benefitmatrix,
        'has_shipment_tracking': has_shipment_tracking,
        'shipments': shipments,
        'helplink': 'sponsors',
        })


def _confirm_benefit(request, benefit):
    with transaction.atomic():
        benefit.confirmed = True
        benefit.save()

        messages.info(request, "Benefit {0} for {1} confirmed.".format(benefit.benefit, benefit.sponsor))

        conference = benefit.sponsor.conference

        # Send email
        for manager in benefit.sponsor.managers.all():
            send_conference_mail(conference,
                                 manager.email,
                                 "Sponsorship benefit confirmed",
                                 'confsponsor/mail/benefit_confirmed.txt',
                                 {
                                     'benefit': benefit.benefit,
                                 },
                                 sender=conference.sponsoraddr,
                                 receivername='{0} {1}'.format(manager.first_name, manager.last_name))
        send_conference_sponsor_notification(
            conference,
            "Sponsorship benefit {0} for {1} has been confirmed".format(benefit.benefit, benefit.sponsor),
            "Sponsorship benefit {0} for {1} has been confirmed".format(benefit.benefit, benefit.sponsor),
        )

        # Potentially send tweet
        if benefit.benefit.tweet_template:
            post_conference_social(conference,
                                   render_sandboxed_template(benefit.benefit.tweet_template, {
                                       'benefit': benefit.benefit,
                                       'level': benefit.benefit.level,
                                       'conference': conference,
                                       'sponsor': benefit.sponsor
                                   }),
                                   approved=True)


def _unclaim_benefit(request, claimed_benefit):
    with transaction.atomic():
        benefit = claimed_benefit.benefit
        sponsor = claimed_benefit.sponsor
        conference = sponsor.conference
        benefitclass = get_benefit_class(benefit.benefit_class)(benefit.level, benefit.class_parameters)
        if not benefitclass.can_unclaim(claimed_benefit):
            messages.error(request, "Benefit {0} cannot be unclaimed".format(benefit))
            return

        # To unclaim a benefit, we delete it, simple as that
        messages.info(request, "Benefit {0} for {1} unclaimed.".format(benefit, sponsor))
        claimed_benefit.delete()

        # Send email
        for manager in sponsor.managers.all():
            send_conference_mail(conference,
                                 manager.email,
                                 "Sponsorship benefit unclaimed",
                                 'confsponsor/mail/benefit_unclaimed.txt',
                                 {
                                     'benefit': benefit,
                                 },
                                 sender=conference.sponsoraddr,
                                 receivername='{0} {1}'.format(manager.first_name, manager.last_name))
        send_conference_sponsor_notification(
            conference,
            "Sponsorship benefit {0} for {1} has been unclaimed".format(benefit, sponsor),
            "Sponsorship benefit {0} for {1} has been unclaimed".format(benefit, sponsor),
        )


@login_required
@transaction.atomic
def sponsor_admin_sponsor(request, confurlname, sponsorid):
    conference = get_authenticated_conference(request, confurlname)

    sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)

    if request.method == 'POST' and request.POST.get('confirm', '0') == '1':
        # Confirm one of the benefits, so do this before we load the list
        benefit = get_object_or_404(SponsorClaimedBenefit, sponsor=sponsor, id=get_int_or_error(request.POST, 'claimid'))
        _confirm_benefit(request, benefit)
        return HttpResponseRedirect('.')

    if request.method == 'POST' and request.POST.get('unclaim', '0') == '1':
        # Unclaim one of the benefits
        benefit = get_object_or_404(SponsorClaimedBenefit, sponsor=sponsor, id=get_int_or_error(request.POST, 'claimid'))
        _unclaim_benefit(request, benefit)
        return HttpResponseRedirect('.')

    if request.method == 'POST':
        if request.POST.get('submit', '') == 'Generate invoice':
            if sponsor.invoice:
                # Existing invoice
                messages.warning(request, "This sponsor already has an invoice!")
                return HttpResponseRedirect(".")

            if sponsor.level.levelcost == 0:
                messages.warning(request, "Should not be possible to generate zero cost invoice, something went wrong!")
                return HttpResponseRedirect(".")

            # Actually generate the invoice!
            manager = sponsor.managers.all()[0]
            sponsor.invoice = create_sponsor_invoice(manager, sponsor)
            sponsor.invoice.save()
            sponsor.save()
            wrapper = InvoiceWrapper(sponsor.invoice)
            wrapper.email_invoice()
            messages.info(request, "Invoice sent to {0}".format(manager.email))
            return HttpResponseRedirect(".")
        if request.POST.get('submit', '') == 'Confirm sponsorship':
            confirm_sponsor(sponsor, request.user.username)
            messages.info(request, "Sponsor {0} confirmed".format(sponsor.name))
            return HttpResponseRedirect(".")
        if request.POST.get('submit', '') == 'Confirm sponsorship without invoice':
            # Directly confirm the sponsorship, since the cost was zero (any payment is assumed
            # to have been handled manually in this case)
            if sponsor.level.levelcost > 0:
                messages.error(request, "Cannot confirm a sponsor with non-zero cost without an inovice!")
                return HttpResponseRedirect(".")
            confirm_sponsor(sponsor, request.user.username)
            messages.info(request, "Sponsor {0} confirmed".format(sponsor.name))
            return HttpResponseRedirect(".")
        if request.POST.get('submit', '') == 'Reject sponsorship':
            if sponsor.invoice:
                messages.warning(request, "Cannot reject sponsorship with an invoice!")
                return HttpResponseRedirect(".")
            reason = request.POST.get('reason', '')
            if len(reason) < 5:
                messages.error(request, "Cannot reject sponsorship without reason!")
                return HttpResponseRedirect(".")
            # Else actually reject it
            send_conference_sponsor_notification(
                conference,
                "Sponsor %s rejected" % sponsor.name,
                "The sponsor {0} has been rejected by {1}.\nThe reason given was: {2}".format(sponsor.name, request.user, reason),
            )
            for manager in sponsor.managers.all():
                send_conference_mail(conference,
                                     manager.email,
                                     "Sponsorship removed",
                                     'confsponsor/mail/sponsor_rejected.txt',
                                     {
                                         'sponsor': sponsor,
                                         'conference': conference,
                                         'reason': reason,
                                     },
                                     sender=conference.sponsoraddr,
                                     receivername='{0} {1}'.format(manager.first_name, manager.last_name))

            messages.info(request, "Sponsor {0} rejected.".format(sponsor.name))
            sponsor.delete()
            return HttpResponseRedirect("../")

        # Any other POST we don't know what it is
        return HttpResponseRedirect(".")

    unclaimedbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=False).exclude(sponsorclaimedbenefit__sponsor=sponsor)
    claimedbenefits = SponsorClaimedBenefit.objects.filter(sponsor=sponsor).order_by('confirmed', 'benefit__sortkey')
    noclaimbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=True)

    for b in claimedbenefits:
        if b.benefit.benefit_class:
            c = get_benefit_class(b.benefit.benefit_class)(sponsor.level, b.benefit.class_parameters)
            b.claimhtml = c.render_claimdata(b)
            if b.confirmed:
                b.can_unclaim = c.can_unclaim(b)
            else:
                b.can_unclaim = True

    return render(request, 'confsponsor/admin_sponsor.html', {
        'conference': conference,
        'sponsor': sponsor,
        'claimedbenefits': claimedbenefits,
        'unclaimedbenefits': unclaimedbenefits,
        'noclaimbenefits': noclaimbenefits,
        'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
        'euvat': settings.EU_VAT,
        'helplink': 'sponsors',
        })


@login_required
def sponsor_admin_benefit(request, confurlname, benefitid):
    conference = get_authenticated_conference(request, confurlname)

    benefit = get_object_or_404(SponsorClaimedBenefit, id=benefitid, sponsor__conference=conference)
    if benefit.benefit.benefit_class:
        claimdata = get_benefit_class(benefit.benefit.benefit_class)(benefit.benefit.level, benefit.benefit.class_parameters).render_claimdata(benefit)
    else:
        claimdata = None

    if request.method == 'POST' and request.POST.get('confirm', '') == '1':
        # Confirm this benefit!
        _confirm_benefit(request, benefit)
        return HttpResponseRedirect('.')

    if request.method == 'POST' and request.POST.get('unclaim', '') == '1':
        # Un-claim this benefit. That means we just remove the SponsorClaimedBenefit entry
        benefit.delete()
        messages.info(request, "The benefit {0} has been un-claimed from {1}".format(benefit.benefit, benefit.sponsor))
        return HttpResponseRedirect('../../')

    return render(request, 'confsponsor/admin_benefit.html', {
        'conference': conference,
        'sponsor': benefit.sponsor,
        'benefit': benefit,
        'claimdata': claimdata,
        'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
        'helplink': 'sponsors',
        })


@login_required
@transaction.atomic
def sponsor_admin_send_mail(request, confurlname):
    conference = get_authenticated_conference(request, confurlname)

    sendto = request.GET.get('sendto', '') or request.POST.get('sendto', '')
    if sendto not in ('', 'level', 'sponsor'):
        return HttpResponseRedirect(".")

    if request.method == 'POST':
        form = SponsorSendEmailForm(conference, sendto, data=request.POST)
        if form.is_valid():
            # Create a message record
            msg = SponsorMail(conference=conference,
                              subject=form.data['subject'],
                              message=form.data['message'])
            msg.save()
            if sendto == 'level':
                for l in form.data.getlist('levels'):
                    msg.levels.add(l)
                sponsors = Sponsor.objects.filter(conference=conference, level__in=form.data.getlist('levels'), confirmed=True)
                deststr = "sponsorship levels {0}".format(", ".join([l.levelname for l in msg.levels.all()]))
            else:
                for s in form.data.getlist('sponsors'):
                    msg.sponsors.add(s)
                sponsors = Sponsor.objects.filter(conference=conference, pk__in=form.data.getlist('sponsors'))
                deststr = "sponsors {0}".format(", ".join([s.name for s in msg.sponsors.all()]))
            msg.save()

            # Now also send the email out to the *current* subscribers
            for sponsor in sponsors:
                for manager in sponsor.managers.all():
                    send_conference_mail(conference,
                                         manager.email,
                                         msg.subject,
                                         'confsponsor/mail/sponsor_mail.txt',
                                         {
                                             'body': msg.message,
                                             'sponsor': sponsor,
                                         },
                                         sender=conference.sponsoraddr,
                                         receivername='{0} {1}'.format(manager.first_name, manager.last_name))
                # And possibly send it out to the extra address for the sponsor
                if sponsor.extra_cc:
                    send_conference_mail(conference,
                                         sponsor.extra_cc,
                                         msg.subject,
                                         'confsponsor/mail/sponsor_mail.txt',
                                         {
                                             'body': msg.message,
                                             'sponsor': sponsor,
                                         },
                                         sender=conference.sponsoraddr,
                    )

            send_conference_sponsor_notification(
                conference,
                "Email sent to sponsors",
                """An email was sent to sponsors of {0}
with subject '{1}'.

It was sent to {2}.

------
{3}
------

To view it on the site, go to {4}/events/sponsor/admin/{5}/viewmail/{6}/""".format(
                    conference,
                    msg.subject,
                    deststr,
                    msg.message,
                    settings.SITEBASE,
                    conference.urlname,
                    msg.id,
                ),
            )

            messages.info(request, "Email sent to %s sponsors, and added to their sponsor pages" % len(sponsors))
            return HttpResponseRedirect("../")
    else:
        if sendto == 'sponsor' and request.GET.get('preselectsponsors', ''):
            initial_sponsors = Sponsor.objects.filter(conference=conference, pk__in=request.GET.getlist('preselectsponsors'))
        else:
            initial_sponsors = None
        form = SponsorSendEmailForm(conference, sendto, initial={
            'sponsors': initial_sponsors,
        })

    return render(request, 'confsponsor/sendmail.html', {
        'conference': conference,
        'form': form,
        'sendto': sendto,
        'mails': SponsorMail.objects.prefetch_related('levels', 'sponsors').filter(conference=conference).order_by('sentat'),
        'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
        'helplink': 'sponsors',
    })


@login_required
def sponsor_admin_view_mail(request, confurlname, mailid):
    conference = get_authenticated_conference(request, confurlname)

    mail = get_object_or_404(SponsorMail, conference=conference, id=mailid)
    return render(request, 'confsponsor/sent_mail.html', {
        'conference': conference,
        'mail': mail,
        'admin': True,
        'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
        'helplink': 'sponsors',
        })


@login_required
def sponsor_admin_imageview(request, benefitid):
    # Image is fetched as part of a benefit, so find the benefit

    benefit = get_object_or_404(SponsorClaimedBenefit, id=benefitid)
    if not request.user.is_superuser:
        # Check permissions for non superusers
        if not benefit.sponsor.conference.administrators.filter(pk=request.user.id).exists() and not benefit.sponsor.conference.series.administrators.filter(pk=request.user.id).exists():
            # Finally, can actually be viewed by the managers of the
            # sponsor itself.
            if not benefit.sponsor.managers.filter(pk=request.user.id).exists():
                return HttpResponseForbidden("Access denied")

    # If the benefit existed, we have verified the permissions, so we can now show
    # the image itself.
    storage = InlineEncodedStorage('benefit_image')

    # XXX: do we need to support non-png at some point? store info in claimdata!
    resp = HttpResponse(content_type='image/png')
    resp.write(storage.read(benefit.id))
    return resp


@superuser_required
def sponsor_admin_test_vat(request, confurlname):
    # Just verify the conference exists and we have permissions
    get_authenticated_conference(request, confurlname)

    vn = request.POST.get('vatnumber', '')
    if not vn:
        return HttpResponse("Empty search")

    r = validate_eu_vat_number(vn.upper().replace(' ', ''))
    if r:
        return HttpResponse("VAT validation error: %s" % r)
    return HttpResponse("VAT number is valid")


@login_required
@transaction.atomic
def sponsor_admin_refund(request, confurlname, sponsorid):
    conference = get_authenticated_conference(request, confurlname)
    sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)
    invoice = sponsor.invoice
    sponsorname = sponsor.name

    if invoice:
        if not invoice.paidat:
            messages.error(request, "Sponsorship invoice has not been paid, not refundable")
            return HttpResponseRedirect("../")

        if len(invoice.invoicerow_set.values('vatrate').distinct()) > 1:
            messages.error(request, "Invoice is using a mix of VAT rates, cannot refund")
            return HttpResponseRedirect("../")

    if request.method == 'POST':
        form = SponsorRefundForm(data=request.POST)
        if form.is_valid():
            class _AbortValidation(Exception):
                pass

            try:
                # Additional validations based on which type of review (basic form
                # validation has already been done in the form class and passed)
                if form.cleaned_data['refundamount'] != "2":
                    if not invoice:
                        form.add_error('refundamount', "Sponsorship does not have an invoice! There is nothing to refund!")
                        raise _AbortValidation()

                if invoice:
                    total_refunds = invoice.total_refunds
                else:
                    total_refunds = None

                if form.cleaned_data['refundamount'] == "0":
                    # Refund the full invoice
                    if total_refunds['amount']:
                        form.add_error('refundamount', "Parts of this invoice has already been refunded, can't do a full refund any longer")
                elif form.cleaned_data['refundamount'] == "1":
                    # Custom amount
                    if form.cleaned_data['customrefundamount'] > total_refunds['remaining']['amount']:
                        form.add_error('customrefundamount', "Only {} {} non-vat remains to be refunded on this invoice".format(settings.CURRENCY_SYMBOL, total_refunds['remaining']['amount']))
                    if settings.EU_VAT and form.cleaned_data['customrefundamountvat'] > total_refunds['remaining']['vatamount']:
                        form.add_error('customrefundamountvat', "Only {} {} VAT remains to be refunded on this invoice".format(settings.CURRENCY_SYMBOL, total_refunds['remaining']['vatamount']))
                elif form.cleaned_data['refundamount'] == "2":
                    # No refund, just cancel
                    if form.cleaned_data['cancelmethod'] == "1":
                        form.add_error('refundamount', "When not issuing a refund, also not canceling becomes a no-op")
                        form.add_error('cancelmethod', "When not issuing a refund, also not canceling becomes a no-op")
                else:
                    form.add_error('refundamount', 'Invalid option selected')

                if form.errors:
                    raise _AbortValidation()

                spoint = transaction.savepoint()
                try:
                    oplog = io.StringIO()

                    # Start by canceling the sponsorship, if set to
                    if form.cleaned_data['cancelmethod'] == "0":
                        managers = [(m.email, '{0} {1}'.format(m.first_name, m.last_name)) for m in sponsor.managers.all()]

                        oplog.write("Canceling sponsorship for {}.\n".format(sponsorname))

                        # Start by sending a notification email before we start removing things. If
                        # something goes wrong it's just inserts into the database so it will get
                        # rolled back.
                        for e, n in managers:
                            send_conference_mail(sponsor.conference,
                                                 e,
                                                 'Conference sponsorship for {} canceled'.format(sponsor.name),
                                                 'confsponsor/mail/sponsor_canceled.txt',
                                                 {
                                                     'sponsor': sponsor,
                                                 },
                                                 sender=sponsor.conference.sponsoraddr,
                                                 bcc=sponsor.conference.sponsoraddr,
                                                 receivername=n,
                                                 sendername=sponsor.conference.conferencename)

                        # Notify about any confirmed benefits, and automatically remove them,
                        # but don't bother tracking downstream benefits from them, the operator
                        # will deal with that.
                        for b in SponsorClaimedBenefit.objects.filter(sponsor=sponsor, declined=False, confirmed=True):
                            oplog.write(" * Already confirmed benefit {} now removed.\n".format(b.benefit.benefitname))

                        # Re-assign any voucher orders, batches and discount codes to be without a sponsor
                        for v in PurchasedVoucher.objects.filter(sponsor=sponsor):
                            v.sponsor = None
                            v.save()
                            oplog.write(" * Prepaid voucher order {} unassigned, but batch *NOT* deleted.\n".format(v.batch))

                        for b in PrepaidBatch.objects.filter(sponsor=sponsor):
                            b.sponsor = None
                            b.save()
                            oplog.write(" * Prepaid batch {} unassigned, but vouchers *NOT* deleted.\n".format(b.id))

                        for c in DiscountCode.objects.filter(sponsor=sponsor):
                            d.sponsor = None
                            d.save()
                            oplog.write(" * Discount code {} unassigned, but usage *NOT* deleted.\n".format(d.code))

                        # Delete any shipments
                        for s in Shipment.objects.filter(sponsor=sponsor):
                            s.sponsor = None
                            s.save()
                            oplog.write(" * Shipment {} reassigned to conference organizers, remove manually\n".format(s.addresstoken))

                        # Automatically delete, without logging, sponsor scanners, sponsor
                        # managers and scanned attendees.

                        oplog.write("Sponsorship canceled, notifications sent to {} managers.\n".format(len(managers)))

                        sponsor.delete()
                        messages.info(request, "Canceled and removed sponsor {}".format(sponsorname))
                    else:
                        oplog.write("Refunding sponsorship for {} WITHOUT canceling the sponsorship.\n".format(sponsorname))

                    oplog.write("\n")

                    # Now issue the refund of the invoice
                    to_refund = to_refund_vat = 0
                    if form.cleaned_data['refundamount'] == "0":
                        # Refund the full invoice
                        to_refund = invoice.total_amount - invoice.total_vat
                        to_refund_vat = invoice.total_vat
                        oplog.write("Preparing refund of the full invoice.\n")
                    elif form.cleaned_data['refundamount'] == "1":
                        # Refund the specific amount
                        to_refund = form.cleaned_data['customrefundamount']
                        if settings.EU_VAT:
                            to_refund_vat = form.cleaned_data['customrefundamountvat']
                        else:
                            to_refund_vat = 0
                        oplog.write("Preparing refund of {} {} + {} {} VAT.\n".format(settings.CURRENCY_SYMBOL, to_refund, settings.CURRENCY_SYMBOL, to_refund_vat))
                    else:
                        # No refund
                        oplog.write("NO REFUND issued for this cancelation.\n")

                    if to_refund:
                        manager = InvoiceManager()
                        manager.refund_invoice(invoice, 'Sponsorship canceled', to_refund, to_refund_vat, conference.vat_sponsorship)
                        oplog.write("Issued refund of {} {} + {} {} VAT for invoice #{}.\n".format(settings.CURRENCY_SYMBOL, to_refund, settings.CURRENCY_SYMBOL, to_refund_vat, invoice.id))

                    # Send a notification email to the organizers with the full details
                    # of the cancelation.
                    send_conference_sponsor_notification(
                        conference,
                        "Sponsor {} canceled by {}".format(sponsorname, request.user.username),
                        oplog.getvalue(),
                    )

                    transaction.savepoint_commit(spoint)

                    if form.cleaned_data['cancelmethod'] == "0":
                        # Sponsorship canceled, so we need to redirect to sponsorship dashboard
                        return HttpResponseRedirect("../../")
                    else:
                        # Sponsorship not actually canceled, so redirect back to sponsor
                        return HttpResponseRedirect("../")

                except Exception as e:
                    form.add_error(None, "Error trying to refund/cancel: {}".format(e))
                    transaction.savepoint_rollback(spoint)

            except _AbortValidation:
                # Fall through and re-render form
                pass
    else:
        form = SponsorRefundForm()

    return render(request, 'confsponsor/admin_sponsor_refund.html', {
        'conference': conference,
        'sponsor': sponsor,
        'form': form,
        'savebutton': 'Refund and cancel sponsorship',
        'breadcrumbs': [('../../', 'Sponsors'), ('../', sponsor.name), ],
        'helplink': 'sponsors',
    })


@login_required
@transaction.atomic
def sponsor_admin_reissue(request, confurlname, sponsorid):
    conference = get_authenticated_conference(request, confurlname)
    sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)
    invoice = sponsor.invoice

    if not invoice:
        messages.error(request, 'This sponsorship does not have an invoice, there is nothing to reissue!')
        return HttpResponseRedirect('../')

    if invoice.paidat:
        messages.error(request, 'This sponsorship is already paid. Invoice cannot be reissued.')
        return HttpResponseRedirect('../')

    old = {
        'invoiceaddr': invoice.recipient_address,
        'invoicerows': [[i.rowtext, i.rowcount, i.rowamount, i.vatrate] for i in invoice.invoicerow_set.all()],
        'recipient': invoice.recipient_user,
    }
    new = {
        'invoiceaddr': get_sponsor_invoice_address(sponsor.name, sponsor.invoiceaddr, sponsor.vatnumber),
        'invoicerows': get_sponsor_invoice_rows(sponsor),
        'recipient': sponsor.managers.all()[0],
    }
    if len(old['invoicerows']) != 1:
        messages.error(request, 'Old set of invoice rows is not 1 row, unsupported.')
        return HttpResponseRedirect('../')
    if len(new['invoicerows']) != 1:
        messages.error(request, 'New set of invoice rows is not 1 row, unsupported.')
        return HttpResponseRedirect('../')

    if old == new:
        messages.warning(request, 'No invoice details changed, not reissuing invoice. Change invoice information first and try again.')
        return HttpResponseRedirect('../')

    def _get_rowinfo(r):
        if settings.EU_VAT:
            return (
                r[0],
                Decimal(r[2]).quantize(Decimal('0.01')),
                r[3] and "{}%".format(r[3].vatpercent) or None,
                Decimal(r[3] and r[2] + r[2] * r[3].vatpercent / 100 or r[2]).quantize(Decimal('0.01')),
            )
        else:
            return (r[0], r[2])

    old['invoiceinfo'] = _get_rowinfo(old['invoicerows'][0])
    new['invoiceinfo'] = _get_rowinfo(new['invoicerows'][0])
    print(new['invoiceinfo'])

    if request.method == 'POST':
        form = SponsorReissueForm(data=request.POST)
        if form.is_valid():
            # Create the new invoice, overwriting the existing one
            manager = sponsor.managers.all()[0]
            sponsor.invoice = create_sponsor_invoice(manager, sponsor, override_duedate=invoice.duedate)
            sponsor.invoice.save()
            sponsor.save()
            # Send email with the new invoice
            InvoiceWrapper(sponsor.invoice).email_invoice()
            # Now cancel the previous invoice, which will automatically send another email. Before we do
            # that we have to unhook the invoice.
            invoice.processor = None
            invoice.processorid = None
            invoice.save()
            im = InvoiceManager()
            im.cancel_invoice(invoice, 'Invoice is being reissued as #{}'.format(sponsor.invoice.id), request.user)

            # Generate a separate notice to the organizers
            send_conference_sponsor_notification(
                conference,
                "Sponsor {} invoice reissued".format(sponsor.name),
                "The invoice for sponsor {} has been reissued by {}, with changed details.".format(sponsor.name, request.user),
            )

            messages.info(request, "Sponsor invoice reissued.")
            return HttpResponseRedirect("../")
    else:
        form = SponsorReissueForm()

    return render(request, 'confsponsor/admin_sponsor_reissue.html', {
        'conference': conference,
        'sponsor': sponsor,
        'form': form,
        'old': old,
        'new': new,
        'both': [old, new],
        'savebutton': 'Reissue sponsorship invoice',
        'breadcrumbs': [('../../', 'Sponsors'), ('../', sponsor.name), ],
        'helplink': 'sponsors',
    })
