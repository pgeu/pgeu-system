from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone
from django.forms import ValidationError

import json
import os
from decimal import Decimal
from datetime import timedelta
import urllib.parse
from io import BytesIO
import re

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.util.middleware import RedirectException
from postgresqleu.util.time import today_conference
from postgresqleu.util.messaging.util import send_org_notification
from postgresqleu.confreg.jinjafunc import JINJA_TEMPLATE_ROOT, render_jinja_conference_template, render_jinja_conference_response
from postgresqleu.confreg.jinjapdf import render_jinja_ticket
from postgresqleu.invoices.models import InvoiceHistory

from .regtypes import validate_special_reg_type
from .models import PrepaidVoucher, DiscountCode, RegistrationWaitlistHistory
from .models import ConferenceRegistration, Conference, ConferenceSeries
from .models import AttendeeMail
from .models import ConferenceRegistrationLog


def reglog(reg, txt, user=None, data=None):
    if data:
        jdata = json.dumps({k: str(v) for k, v in data.items()}, indent=1)
    else:
        jdata = ''

    if isinstance(reg, ConferenceRegistration):
        ConferenceRegistrationLog(reg=reg, txt=txt, user=user, changedata=jdata).save()
    else:
        ConferenceRegistrationLog(reg_id=reg, txt=txt, user=user, changedata=jdata).save()


#
# Send an email using a conference template
#
def send_conference_mail(conference, receiver, subject, templatename, templateattr={}, attachments=None, bcc=None, receivername=None, sender=None, sendername=None, sendat=None):
    if not ((conference and conference.jinjaenabled and conference.jinjadir) or os.path.exists(os.path.join(JINJA_TEMPLATE_ROOT, templatename))):
        raise Exception("Mail template not found")

    send_simple_mail(sender or conference.contactaddr,
                     receiver,
                     "[{0}] {1}".format(conference.conferencename, subject),
                     render_jinja_conference_template(conference, templatename, templateattr),
                     attachments,
                     bcc,
                     sendername or conference.conferencename,
                     receivername,
                     sendat=sendat,
                     )


def send_conference_simple_mail(conference, receiver, subject, message, attachments=None, bcc=None, receivername=None, sender=None, sendername=None, sendat=None):
    send_simple_mail(sender or conference.contactaddr,
                     receiver,
                     "[{0}] {1}".format(conference.conferencename, subject),
                     message,
                     attachments,
                     bcc,
                     sendername or conference.conferencename,
                     receivername,
                     sendat=sendat,
                     )


class InvoicerowsException(Exception):
    pass


def invoicerows_for_registration(reg, update_used_vouchers):
    # Return the rows that would be used to build an invoice for this
    # registration. Format is tuple of (description, num, cost)

    # Main conference registration
    r = [['%s - %s' % (reg.email, reg.regtype.regtype),
          1,
          reg.regtype.cost,
          reg.conference.vat_registrations,
          ]]

    # Any additional options
    for a in reg.additionaloptions.all():
        if a.cost > 0:
            r.append(['   %s' % a.name, 1, a.cost, reg.conference.vat_registrations])

    # Any voucher if present
    if reg.vouchercode:
        try:
            v = PrepaidVoucher.objects.get(vouchervalue=reg.vouchercode, conference=reg.conference)
            if v.usedate:
                # Find a way to raise an exception here if the voucher is
                # already used? For now, we just ignore it.
                raise InvoicerowsException("Prepaid voucher already used")
            else:
                # Valid voucher found!
                if update_used_vouchers:
                    v.usedate = timezone.now()
                    v.user = reg
                    v.save()
                # Add a row with the discount of the registration type
                r.append(['   Discount voucher %s...' % reg.vouchercode[:30], 1, -reg.regtype.cost, reg.conference.vat_registrations])
        except PrepaidVoucher.DoesNotExist:
            # Nonexistant voucher code means discount code was used
            try:
                d = DiscountCode.objects.get(code=reg.vouchercode, conference=reg.conference)
                if d.validuntil and d.validuntil < today_conference():
                    raise InvoicerowsException("Discount code is no longer valid")
                elif d.maxuses > 0 and d.registrations.count() >= d.maxuses:
                    raise InvoicerowsException("Discount code does not have enough remaining instances")
                elif d.is_invoiced:
                    raise InvoicerowsException("Discount code has already been invoiced and is no longer valid")
                else:
                    # Valid discount code found!
                    selected_options = reg.additionaloptions.all()
                    for o in d.requiresoption.all():
                        if o not in selected_options:
                            raise InvoicerowsException("Discount code requires option {0}".format(o.name))

                    required_regtypes = d.requiresregtype.all()
                    if required_regtypes:
                        if reg.regtype not in required_regtypes:
                            raise InvoicerowsException("Discount code requires registration types {0}".format(",".join(required_regtypes)))

                    if update_used_vouchers:
                        d.registrations.add(reg)
                        d.save()
                    # Add a row with the discount
                    current_total = sum([rr[2] for rr in r])
                    discount = 0
                    if d.discountamount:
                        # Fixed amount discount
                        discount = d.discountamount > current_total and current_total or d.discountamount
                    else:
                        # Percentage discount. Can be either off the total or just the reg
                        if d.regonly:
                            # regtype.cost is Decimal
                            discount = reg.regtype.cost * d.discountpercentage / 100
                        else:
                            discount = Decimal(current_total) * d.discountpercentage / 100
                    if discount > 0:
                        r.append(['   Discount code %s' % d.code, 1, -discount, reg.conference.vat_registrations])
            except DiscountCode.DoesNotExist:
                raise InvoicerowsException("Invalid voucher code")
    return r


def summarize_registration_invoicerows(invoicerows):
    # Add a VAT column and calculate totals
    totalcost = 0
    totalwithvat = 0
    for r in invoicerows:
        if r[1] != 1:
            raise Exception("Registration invoicerows should always have count=1!")

        # Note! Should always be the same as invoices/models.py, InvoiceRow.totalvat otherwise weird discrepancies
        # can show up between previews and invoices!
        if r[3]:
            r.append((r[2] + r[2] * r[3].vatpercent / Decimal(100)).quantize(Decimal('.01')))
        else:
            r.append(r[2])
        totalcost += r[2]
        totalwithvat += r[4]
    return (totalcost, totalwithvat)


def attendee_cost_from_bulk_payment(reg):
    re_email_dash = re.compile(r"^[^\s]+@[^\s]+ - [^\s]")
    if not reg.bulkpayment:
        raise Exception("Not called with bulk payment!")

    # We need to find the individual rows and sum it up, since it's possible that we have been
    # using discount codes for example.
    # We have no better key to work with than the email address...
    found = False
    totalnovat = totalvat = 0
    for r in reg.bulkpayment.invoice.invoicerow_set.all().order_by('id'):
        if r.rowtext.startswith(reg.email + ' - '):
            # Found the beginning!
            if found:
                raise Exception("Found the same registration more than once!")
            found = True
            totalnovat = r.totalrow
            totalvat = r.totalvat
        elif r.rowtext.startswith("  "):
            # Something to do with this reg
            if found:
                totalnovat += r.totalrow
                totalvat += r.totalvat
        elif re_email_dash.match(r.rowtext):
            # Matched a different reg
            found = False
        else:
            raise Exception("Unknown invoice row '%s'" % r.rowtext)

    return (totalnovat, totalvat)


def send_welcome_email(reg):
    # Do we need to send the welcome email?
    if not reg.conference.sendwelcomemail:
        return

    # If policy is required but policy hasn't been confirmed. This could happen if the welcome
    # email is re-sent manually before the policy is confirmed, for example if a registration was
    # made with the wrong email address. In this case, re-send the policy email instead, as confirming
    # the policy will then trigger the welcome email.
    if reg.conference.confirmpolicy and not reg.policyconfirmedat:
        send_policy_email(reg)
        return

    if reg.conference.tickets:
        buf = BytesIO()
        render_jinja_ticket(reg, buf, JINJA_TEMPLATE_ROOT, settings.REGISTER_FONTS)
        attachments = [
            ('{0}_ticket.pdf'.format(reg.conference.urlname), 'application/pdf', buf.getvalue()),
        ]
    else:
        attachments = None

    # Ok, this attendee needs a notification. For now we don't support
    # any string replacements in it, maybe in the future.
    send_conference_mail(reg.conference,
                         reg.email,
                         "Registration complete",
                         'confreg/mail/welcomemail.txt',
                         {
                             'reg': reg,
                         },
                         receivername=reg.fullname,
                         attachments=attachments,
    )


def send_policy_email(reg):
    send_conference_mail(
        reg.conference,
        reg.email,
        "Conference policy",
        'confreg/mail/policymail.txt',
        {
            'reg': reg,
        },
        receivername=reg.fullname,
    )


def send_attachment_email(reg):
    send_conference_mail(
        reg.conference,
        reg.email,
        "Your registration",
        'confreg/mail/regmulti_attach.txt',
        {
            'conference': reg.conference,
            'reg': reg,
        },
        receivername=reg.fullname,
    )


def notify_reg_confirmed(reg, updatewaitlist=True):
    reglog(reg, "Registration confirmed")

    # This one was off the waitlist, so generate a history entry
    if updatewaitlist and hasattr(reg, 'registrationwaitlistentry'):
        RegistrationWaitlistHistory(waitlist=reg.registrationwaitlistentry,
                                    text="Completed registration from the waitlist").save()

    # If this registration has no user attached to it, it means that
    # it was a "register for somebody else". In this case we need to
    # send the user an email with information that otherwise would not
    # be available. This means that the user will get two separate
    # emails in case welcome emails is enabled, but that is necessary
    # since we need to include links and things in this email.
    if not reg.attendee:
        # First we see if we can just find a user match on email, this
        # being a user that has not already registered for this
        # conference.
        found = False
        try:
            u = User.objects.get(email=reg.email)
            if not ConferenceRegistration.objects.filter(conference=reg.conference, attendee=u).exists():
                # Found user by this id, not used yet, so attach it
                # to their account.
                reg.attendee = u
                reg.save()
                found = True
        except User.DoesNotExist:
            pass

        if not found:
            # User not found, so we use the random token and send it
            # to ask them to attach their account to this registration.
            send_attachment_email(reg)

    # If the registration has a user account, we may have email to connect
    # to this registration.
    if reg.attendee:
        for m in AttendeeMail.objects.filter(conference=reg.conference,
                                             pending_regs=reg.attendee):
            m.pending_regs.remove(reg.attendee)
            m.registrations.add(reg)

    if reg.conference.notifyregs:
        send_conference_notification_template(
            reg.conference,
            "New registration",
            'confreg/mail/admin_notify_reg.txt',
            {
                'reg': reg,
            },
        )

    # If this conference has a policy that has to be confirmed, and this isn't
    # already done in the workflow (it will be for a reg-myself account, but it
    # will not be in a bulk payment reg)
    if reg.conference.confirmpolicy and not reg.policyconfirmedat:
        send_policy_email(reg)
    else:
        send_welcome_email(reg)


def cancel_registration(reg, is_unconfirmed=False, reason=None, user=None):
    if reg.canceledat:
        raise Exception("Registration is already canceled")

    # Verify that we're only canceling a real registration
    if not reg.payconfirmedat:
        # If we don't allow canceling an unpaid registration, and the registration
        # actually is unpaid, then boom.
        if not is_unconfirmed:
            raise Exception("Registration not paid, data is out of sync!")

    # If we sent a welcome mail, also send a goodbye mail. Except when this is an
    # unfinished part of a multiregistration, in which case it would probably just
    # be confusing to the user.
    if reg.conference.sendwelcomemail and not (reg.attendee != reg.registrator and not reg.payconfirmedat):
        send_conference_mail(reg.conference,
                             reg.email,
                             "Registration canceled",
                             'confreg/mail/reg_canceled.txt',
                             {
                                 'conference': reg.conference,
                                 'reg': reg,
                                 'unconfirmed': is_unconfirmed,
                             },
                             receivername=reg.fullname,
        )

    # Now actually cancel the reg.

    # If the reg used a voucher or a discount code, return it to the pool.
    if reg.vouchercode:
        if PrepaidVoucher.objects.filter(user=reg).exists():
            v = PrepaidVoucher.objects.get(user=reg)
            v.user = None
            v.usedate = None
            v.save()
        elif DiscountCode.objects.filter(registrations=reg).exists():
            d = DiscountCode.objects.get(registrations=reg)
            d.registrations.remove(reg)
            d.save()
        reg.vouchercode = ""

    # If the registration has any additional options, remove them
    reg.additionaloptions.clear()

    # Volunteer assignments are simply deleted
    reg.volunteerassignment_set.all().delete()

    # If this registration was never paid, we're done now - just delete
    # the record completely. We don't care about keeping registrations
    # that never completed around in history.
    if not reg.payconfirmedat:
        reg.delete()
        return

    # Else, flag canceled and save
    reg.canceledat = timezone.now()
    reg.save()

    reglog(reg, "Canceled registration", user)

    # If the registration is on any signups, remove it from there
    for s in reg.attendeesignup_set.all():
        reglog(reg, "Removed from signup {}".format(s.signup.title))
        s.delete()

    if reg.conference.notifyregs and not is_unconfirmed:
        send_conference_notification_template(
            reg.conference,
            "Canceled registration",
            'confreg/mail/admin_notify_cancel.txt',
            {
                'reg': reg,
                'reason': reason,
            },
        )


def get_invoice_autocancel(*args):
    # Each argument is expected to be an integer with number of hours,
    # or None if there is no limit
    hours = [a for a in args if a is not None]
    if hours:
        return timezone.now() + timedelta(hours=min(hours))
    else:
        return None


def expire_additional_options(reg):
    # If there are any additional options on this registrations that are untouched for
    # longer than the invoice autocancel period, expire them. Send an email to the user
    # being expired (expects to run within a transaction).
    # Returns the list of options expired for this particular user.

    hours = int(round((timezone.now() - reg.lastmodified).total_seconds() / 3600))
    expireset = list(reg.additionaloptions.filter(invoice_autocancel_hours__isnull=False,
                                                  invoice_autocancel_hours__lt=hours))

    expired_names = []
    if expireset:
        # We have something expired. Step one is to send an email about it, based on a
        # template. (It's a bit inefficient to re-parse the template every time, but
        # we don't expire these things very often, so we don't care)

        if reg.attendee:
            send_conference_mail(reg.conference,
                                 reg.email,
                                 'Your pending registration',
                                 'confreg/mail/additionaloption_expired.txt',
                                 {
                                     'conference': reg.conference,
                                     'reg': reg,
                                     'options': expireset,
                                     'optionscount': len(expireset),
                                 },
                                 receivername=reg.fullname,
            )

        for ao in expireset:
            # Notify caller that this one is being expired
            expired_names.append(ao.name)
            # And actually expire it
            reg.additionaloptions.remove(ao)

        # And finally - save
        reg.save()

    return expired_names


def get_authenticated_conference(request, urlname=None, confid=None):
    if not request.user.is_authenticated:
        raise RedirectException("{0}?{1}".format(settings.LOGIN_URL, urllib.parse.urlencode({'next': request.build_absolute_uri()})))

    if confid:
        c = get_object_or_404(Conference, pk=confid)
    else:
        c = get_object_or_404(Conference, urlname=urlname)

    timezone.activate(c.tzname)

    if request.user.is_superuser:
        return c
    else:
        if c.administrators.filter(pk=request.user.id).exists():
            return c
        if c.series.administrators.filter(pk=request.user.id).exists():
            return c
        raise PermissionDenied()


def get_authenticated_series(request, seriesid):
    if not request.user.is_authenticated:
        raise RedirectException("{0}?{1}".format(settings.LOGIN_URL, urllib.parse.urlencode({'next': request.build_absolute_uri()})))

    s = get_object_or_404(ConferenceSeries, pk=seriesid)
    if request.user.is_superuser:
        return s
    else:
        if s.administrators.filter(pk=request.user.id).exists():
            return s
        raise PermissionDenied()


def get_conference_or_404(urlname):
    conference = get_object_or_404(Conference, urlname=urlname)

    timezone.activate(conference.tzname)

    return conference


def activate_conference_timezone(conference):
    timezone.activate(conference.tzname)


def send_conference_notification(conference, subject, message):
    if conference.notifyaddr:
        send_simple_mail(conference.notifyaddr,
                         conference.notifyaddr,
                         subject,
                         message,
                         sendername=conference.conferencename)
    send_org_notification(conference, message)


def send_conference_notification_template(conference, subject, templatename, templateattr):
    if not ((conference and conference.jinjaenabled and conference.jinjadir) or os.path.exists(os.path.join(JINJA_TEMPLATE_ROOT, templatename))):
        raise Exception("Mail template not found")
    message = render_jinja_conference_template(conference, templatename, templateattr)

    send_conference_notification(conference, subject, message)


#
# Render a conference page. It will load the template using the jinja system
# if the conference is configured for jinja templates.
#
def render_conference_response(request, conference, pagemagic, templatename, dictionary=None):
    if conference and conference.jinjaenabled and conference.jinjadir:
        return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

    # At this point all conference templates are in jinja except the admin ones, and admin does not render
    # through render_conference_response(). Thus, if it's not here now, we can 404.
    if os.path.exists(os.path.join(JINJA_TEMPLATE_ROOT, templatename)):
        return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

    raise Http404("Template not found")


#
# Transfer a registration - the plumbing parts
#
def make_registration_transfer(fromreg, toreg, user, complete_transfer=False):
    yield "Initiating transfer from %s to %s" % (fromreg.fullname, toreg.fullname)
    if fromreg.canceledat:
        raise ValidationError("Source registration is canceled!")
    if fromreg.wikipage_set.exists():
        raise ValidationError("Source registration is the author of wiki pages")
    if fromreg.signup_set.exists():
        raise ValidationError("Source registration is the author of signups")
    if toreg.payconfirmedat:
        raise ValidationError("Destination registration is already confirmed!")
    if toreg.canceledat:
        raise ValidationError("Destination registration is canceled!")
    if toreg.bulkpayment:
        raise ValidationError("Destination registration is part of a bulk payment")
    if toreg.invoice:
        raise ValidationError("Destination registration has an invoice")
    if not complete_transfer:
        if fromreg.transfer_from_reg.exists() or fromreg.transfer_to_reg.exists():
            raise ValidationError("Source registration is already part of a transfer")
        if toreg.transfer_from_reg.exists() or toreg.transfer_to_reg.exists():
            raise ValidationError("Destination registration is already part of a transfer")

    if toreg.additionaloptions.exists():
        raise ValidationError("Destination registration has additional options")

    if hasattr(toreg, 'registrationwaitlistentry'):
        yield "Destination registration is on waitlist, canceling"
        toreg.registrationwaitlistentry.delete()

    # Transfer registration type
    if toreg.regtype != fromreg.regtype:
        yield "Change registration type from %s to %s" % (toreg.regtype, fromreg.regtype)
        if fromreg.regtype.specialtype:
            try:
                validate_special_reg_type(fromreg.regtype.specialtype, toreg)
            except ValidationError as e:
                raise ValidationError("Registration type cannot be transferred: %s" % e.message)
        toreg.regtype = fromreg.regtype

    # Transfer any vouchers
    if fromreg.vouchercode != toreg.vouchercode:
        yield "Change discount code to %s" % fromreg.vouchercode
        if toreg.vouchercode:
            # There's already a code set. Remove it.
            toreg.vouchercode = None

            # Actively attached to a discount code. Can't deal with that
            # right now.
            if toreg.discountcode_set.exists():
                raise ValidationError("Receiving registration is connected to discount code. Cannot handle.")
        if fromreg.vouchercode:
            # It actually has one. So we have to transfer it
            toreg.vouchercode = fromreg.vouchercode
            dcs = fromreg.discountcode_set.all()
            if dcs:
                # It's a discount code. There can only ever be one.
                d = dcs[0]
                d.registrations.remove(fromreg)
                d.registrations.add(toreg)
                d.save()
                yield "Transferred discount code %s" % d
            vcs = fromreg.prepaidvoucher_set.all()
            if vcs:
                # It's a voucher code. Same here, only one.
                v = vcs[0]
                v.user = toreg
                v.save()

    # Bulk payment?
    if fromreg.bulkpayment:
        yield "Transfer bulk payment %s" % fromreg.bulkpayment.id
        toreg.bulkpayment = fromreg.bulkpayment
        fromreg.bulkpayment = None
        fromreg.save(update_fields=['bulkpayment'])

    # Invoice?
    if fromreg.invoice:
        yield "Transferring invoice %s" % fromreg.invoice.id
        invoice = fromreg.invoice
        fromreg.invoice = None
        toreg.invoice = invoice
        InvoiceHistory(invoice=toreg.invoice,
                       txt="Transferred from {0} to {1}".format(fromreg.email, toreg.email)
                       ).save()
        fromreg.save(update_fields=['invoice'])

    # Additional options
    if fromreg.additionaloptions.exists():
        for o in fromreg.additionaloptions.all():
            yield "Transferring additional option {0}".format(o)
            o.conferenceregistration_set.remove(fromreg)
            o.conferenceregistration_set.add(toreg)
            o.save()

    # Waitlist entries
    if hasattr(fromreg, 'registrationwaitlistentry'):
        wle = fromreg.registrationwaitlistentry
        yield "Transferring registration waitlist entry"
        wle.registration = toreg
        wle.save()

    yield "Resetting registration date"
    toreg.created = timezone.now()

    yield "Copying payment confirmation"
    toreg.payconfirmedat = fromreg.payconfirmedat
    toreg.payconfirmedby = "{0}(x)".format(fromreg.payconfirmedby)[:16]
    toreg.save()
    reglog(toreg, "Transferred registration from {}".format(fromreg.fullname), user)

    yield "Sending notification to target registration"
    # This notify will also send a ticket or a "confirm conference policy request"
    # depending on the conference configuration.
    notify_reg_confirmed(toreg, False)

    yield "Sending notification to source registration"
    send_conference_mail(fromreg.conference,
                         fromreg.email,
                         "Registration transferred",
                         'confreg/mail/reg_transferred.txt', {
                             'conference': fromreg.conference,
                             'toreg': toreg,
                         },
                         receivername=fromreg.fullname)

    send_conference_notification(
        fromreg.conference,
        "Transferred registration",
        "Registration for {0} transferred to {1}.\n".format(fromreg.email, toreg.email),
    )

    yield "Deleting old registration"
    fromreg.delete()
