#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core import paginator
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponse, Http404
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.db import transaction, connection
from django.db.models import Q, Count, Avg
from django.db.models.expressions import F
from django.forms import ValidationError
from django.utils import timezone
from django.template.defaultfilters import slugify

from .models import Conference, ConferenceRegistration, ConferenceSession, ConferenceSeries
from .models import ConferenceRegistrationLog
from .models import ConferenceSessionSlides, ConferenceSessionVote, GlobalOptOut
from .models import ConferenceSessionFeedback, Speaker
from .models import ConferenceSessionTag
from .models import ConferenceFeedbackQuestion, ConferenceFeedbackAnswer
from .models import RegistrationType, PrepaidVoucher, PrepaidBatch, RefundPattern
from .models import BulkPayment, Room, Track, ConferenceSessionScheduleSlot
from .models import AttendeeMail, ConferenceAdditionalOption
from .models import PendingAdditionalOrder
from .models import RegistrationWaitlistEntry, RegistrationWaitlistHistory
from .models import STATUS_CHOICES
from .models import ConferenceNews, ConferenceTweetQueue
from .models import SavedReportDefinition
from .models import ConferenceMessaging
from .models import CrossConferenceEmail, CrossConferenceEmailRule, CrossConferenceEmailRecipient
from .forms import ConferenceRegistrationForm, RegistrationChangeForm, ConferenceSessionFeedbackForm
from .forms import ConferenceFeedbackForm, SpeakerProfileForm
from .forms import CallForPapersForm
from .forms import CallForPapersCopyForm, PrepaidCreateForm
from .forms import CrossConferenceMailForm
from .forms import AttendeeMailForm, WaitlistOfferForm, WaitlistSendmailForm, TransferRegForm
from .forms import NewMultiRegForm, MultiRegInvoiceForm
from .forms import SessionSlidesUrlForm, SessionSlidesFileForm
from .util import invoicerows_for_registration, notify_reg_confirmed, InvoicerowsException
from .util import get_invoice_autocancel, cancel_registration, send_welcome_email
from .util import attendee_cost_from_bulk_payment
from .util import send_conference_mail, send_conference_notification, send_conference_notification_template
from .util import reglog

from .models import get_status_string, get_status_string_short, valid_status_transitions
from .regtypes import confirm_special_reg_type, validate_special_reg_type
from .jinjafunc import render_jinja_conference_response, JINJA_TEMPLATE_ROOT
from .jinjafunc import render_jinja_conference_template
from .jinjafunc import render_jinja_conference_svg
from .jinjapdf import render_jinja_ticket
from .util import get_authenticated_conference, get_conference_or_404
from .backendforms import CancelRegistrationForm, ConfirmRegistrationForm
from .backendforms import ResendWelcomeMailForm

from postgresqleu.util.request import get_int_or_error
from postgresqleu.util.random import generate_random_token
from postgresqleu.util.time import today_conference
from postgresqleu.util.messaging import get_messaging
from postgresqleu.util.pagination import simple_pagination
from postgresqleu.invoices.util import InvoiceWrapper
from postgresqleu.confwiki.models import Wikipage
from postgresqleu.confsponsor.models import ScannedAttendee, PurchasedVoucher
from postgresqleu.confsponsor.invoicehandler import create_voucher_invoice
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor, InvoiceHistory
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.util.jsonutil import JsonSerializer
from postgresqleu.util.db import exec_to_dict, exec_to_grouped_dict, exec_to_keyed_dict
from postgresqleu.util.db import exec_no_result, exec_to_list, exec_to_scalar, conditional_exec_to_scalar
from postgresqleu.util.db import ensure_conference_timezone
from postgresqleu.util.qr import generate_base64_qr

from decimal import Decimal
from operator import itemgetter
from datetime import timedelta
import base64
import re
import os
from Cryptodome.Hash import SHA256
from io import StringIO
import xml.etree.ElementTree as ET

import json
import markdown


#
# Render a conference page. It will load the template using the jinja system
# if the conference is configured for jinja templates.
#
def render_conference_response(request, conference, pagemagic, templatename, dictionary=None):
    if conference and conference.jinjadir:
        # If a jinjadir is defined, then *always* use jinja.
        return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

    # At this point all conference templates are in jinja except the admin ones, and admin does not render
    # through render_conference_response(). Thus, if it's not here now, we can 404.
    if os.path.exists(os.path.join(JINJA_TEMPLATE_ROOT, templatename)):
        return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

    raise Http404("Template not found")


def _get_registration_signups(conference, reg):
    # Left join is hard to do efficiently with the django ORM, so let's do a query instead
    with ensure_conference_timezone(conference) as cursor:
        cursor.execute("SELECT s.id, s.title, s.deadline, s.deadline < CURRENT_TIMESTAMP, ats.saved, ats.id FROM confwiki_signup s LEFT JOIN confwiki_attendeesignup ats ON (s.id=ats.signup_id AND ats.attendee_id=%(regid)s) WHERE s.conference_id=%(confid)s AND (s.deadline IS NULL OR s.deadline > CURRENT_TIMESTAMP OR ats.saved IS NOT NULL) AND (s.public OR EXISTS (SELECT 1 FROM confwiki_signup_attendees sa WHERE sa.signup_id=s.id AND sa.conferenceregistration_id=%(regid)s) OR EXISTS (SELECT 1 FROM confwiki_signup_regtypes sr WHERE sr.signup_id=s.id AND sr.registrationtype_id=%(regtypeid)s)) ORDER  BY 4 DESC, 3, 2", {
            'confid': conference.id,
            'regid': reg.id,
            'regtypeid': reg.regtype_id,
        })
    return [dict(list(zip(['id', 'title', 'deadline', 'closed', 'savedat', 'respid'], r))) for r in cursor.fetchall()]


# Return a queryset with all the emails this attendee has permissions to see.
# Should then be extended with whatever other requirements there are to limit
# what's actually returned.
def _attendeemail_queryset(conference, reg):
    return AttendeeMail.objects.filter(conference=conference).extra(where=["""
 EXISTS (SELECT 1 FROM confreg_attendeemail_regclasses rc WHERE rc.attendeemail_id=confreg_attendeemail.id AND registrationclass_id=%s)
OR
 EXISTS (SELECT 1 FROM confreg_attendeemail_addopts ao INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceadditionaloption_id=ao.conferenceadditionaloption_id WHERE ao.attendeemail_id=confreg_attendeemail.id AND rao.conferenceregistration_id=%s)
OR
 EXISTS (SELECT 1 FROM confreg_attendeemail_registrations r WHERE r.attendeemail_id=confreg_attendeemail.id AND conferenceregistration_id=%s)
OR
 (tovolunteers AND EXISTS (SELECT 1 FROM confreg_conference_volunteers cv WHERE cv.conference_id=confreg_attendeemail.conference_id AND cv.conferenceregistration_id=%s))
OR
 (tocheckin AND EXISTS (SELECT 1 FROM confreg_conference_checkinprocessors cp WHERE cp.conference_id=confreg_attendeemail.conference_id AND cp.conferenceregistration_id=%s))
""",
    ], params=[reg.regtype.regclass and reg.regtype.regclass.id or None, reg.id, reg.id, reg.id, reg.id])


# Not a view in itself, only called from other views
def _registration_dashboard(request, conference, reg, has_other_multiregs, redir_root):
    if reg.canceledat:
        return render_conference_response(request, conference, 'reg', 'confreg/registration_canceled.html', {
            'redir_root': redir_root,
            'reg': reg,
            'has_other_multiregs': has_other_multiregs,
        })

    mails = _attendeemail_queryset(conference, reg)

    wikipagesQ = Q(publicview=True) | Q(viewer_attendee__attendee=request.user) | Q(viewer_regtype__conferenceregistration__attendee=request.user)
    wikipages = Wikipage.objects.filter(Q(conference=conference) & wikipagesQ).distinct()

    signups = _get_registration_signups(conference, reg)

    is_speaker = ConferenceSession.objects.filter(conference=conference, status=1, speaker__user=request.user).exists()

    # Options available for buy-up. Option must be for this conference,
    # not already picked by this user, and not mutually exclusive to
    # anything picked by this user.
    # Also exclude any option that has a maxcount, and already has too
    # many registrations.
    optionsQ = Q(conference=conference, upsellable=True, public=True) & (Q(maxcount=0) | Q(num_regs__lt=F('maxcount'))) & ~Q(conferenceregistration=reg) & ~Q(mutually_exclusive__conferenceregistration=reg)
    availableoptions = list(ConferenceAdditionalOption.objects.annotate(num_regs=Count('conferenceregistration')).filter(optionsQ))
    try:
        pendingadditional = PendingAdditionalOrder.objects.get(reg=reg, payconfirmedat__isnull=True)
        pendingadditionalinvoice = InvoicePresentationWrapper(pendingadditional.invoice, '.')
    except PendingAdditionalOrder.DoesNotExist:
        pendingadditional = None
        pendingadditionalinvoice = None

    # Any invoices that should be linked need to be added
    invoices = []
    if reg.invoice:
        invoices.append(('Registration invoice and receipt', InvoicePresentationWrapper(reg.invoice, '.')))
    for pao in PendingAdditionalOrder.objects.filter(reg=reg, invoice__isnull=False):
        invoices.append(('Additional options invoice and receipt', InvoicePresentationWrapper(pao.invoice, '.')))

    # Form for changeable fields (only available unless canceled, so make doubly sure)
    if request.method == 'POST' and not reg.canceledat:
        changeform = RegistrationChangeForm(conference.allowedit, instance=reg, data=request.POST)
        if changeform.is_valid():
            changeform.save()
            reglog(reg, "Registration details updated", request.user)
            messages.info(request, "Registration updated.")
            return HttpResponseRedirect("../")
    else:
        changeform = RegistrationChangeForm(conference.allowedit, instance=reg)

    fields = ['shirtsize', 'dietary', 'nick', 'twittername', 'badgescan', 'shareemail', 'photoconsent']
    for f in conference.remove_fields:
        fields.remove(f)
    displayfields = [(reg._meta.get_field(k).verbose_name.capitalize(), reg.get_field_string(k)) for k in fields]

    if conference.askbadgescan:
        scanned_by_sponsors = ScannedAttendee.objects.select_related('sponsor').filter(attendee=reg)
    else:
        scanned_by_sponsors = None

    messaging = ConferenceMessaging.objects.filter(Q(notification=True) | Q(privatebcast=True), conference=conference)
    if reg.messaging:
        t, c = get_messaging(reg.messaging.provider).get_attendee_string(reg.regtoken, reg.messaging, reg.messaging_config)
        if c is None:
            current_messaging_info = t
        else:
            current_messaging_info = render_jinja_conference_template(conference, 'confreg/messaging/{}'.format(t), c)
    else:
        current_messaging_info = ''

    return render_conference_response(request, conference, 'reg', 'confreg/registration_dashboard.html', {
        'redir_root': redir_root,
        'reg': reg,
        'is_speaker': is_speaker,
        'has_other_multiregs': has_other_multiregs,
        'mails': mails,
        'wikipages': wikipages,
        'signups': signups,
        'availableoptions': availableoptions,
        'pendingadditional': pendingadditional,
        'pendingadditionalinvoice': pendingadditionalinvoice,
        'invoices': invoices,
        'scanned_by_sponsors': scanned_by_sponsors,
        'changeform': changeform,
        'displayfields': displayfields,
        'current_messaging_info': current_messaging_info,
        'messaging': messaging,
    })


def confhome(request, confname):
    conference = get_conference_or_404(confname)

    # If there is a registration, redirect to the registration dashboard.
    # If not, or if the user is not logged in, redirect to the conference homepage.
    if request.user.is_authenticated:
        if ConferenceRegistration.objects.filter(conference=conference, attendee=request.user).exists():
            return HttpResponseRedirect('register/')

    return HttpResponseRedirect(conference.confurl)


def news_json(request, confname):
    conference = get_conference_or_404(confname)
    news = ConferenceNews.objects.select_related('author').filter(conference=conference,
                                                                  datetime__lt=timezone.now(),
    )[:5]

    r = HttpResponse(json.dumps(
        [{
            'id': n.id,
            'title': n.title,
            'titleslug': slugify(n.title),
            'datetime': timezone.localtime(n.datetime),
            'authorname': n.author.fullname,
            'summary': markdown.markdown(n.summary),
            'inrss': n.inrss,
        } for n in news],
        cls=JsonSerializer), content_type='application/json')

    r['Access-Control-Allow-Origin'] = '*'
    return r


def news_index(request, confname):
    conference = get_conference_or_404(confname)
    news = ConferenceNews.objects.select_related('author').filter(conference=conference,
                                                                  datetime__lt=timezone.now())

    return render_conference_response(request, conference, 'news', 'confreg/newsindex.html', {
        'news': news,
    })


def news_page(request, confname, newsid):
    conference = get_conference_or_404(confname)
    news = get_object_or_404(ConferenceNews, pk=newsid, conference=conference, datetime__lt=timezone.now())

    return render_conference_response(request, conference, 'news', 'confreg/newsitem.html', {
        'news': news,
    })


@login_required
@transaction.atomic
def register(request, confname, whatfor=None):
    conference = get_conference_or_404(confname)
    if whatfor:
        whatfor = whatfor.rstrip('/')
        redir_root = '../'
    else:
        redir_root = ''

    has_other_multiregs = ConferenceRegistration.objects.filter(Q(conference=conference, registrator=request.user) & ~Q(attendee=request.user)).exists()
    if (not whatfor) and has_other_multiregs and \
       not ConferenceRegistration.objects.filter(conference=conference, attendee=request.user).exists():
        return HttpResponseRedirect('other/')

    # Either not specifying or registering for self.
    try:
        reg = ConferenceRegistration.objects.get(conference=conference,
                                                 attendee=request.user)
    except ConferenceRegistration.DoesNotExist:
        # No previous registration exists. Let the user choose what to
        # do. If already under "self" suburl, copy the data from the
        # user profile and move on.
        if whatfor is None:
            return render_conference_response(request, conference, 'reg', 'confreg/prompt_regfor.html')

        # No previous registration, grab some data from the user profile
        reg = ConferenceRegistration(conference=conference, attendee=request.user, registrator=request.user)
        reg.email = request.user.email.lower()
        reg.firstname = request.user.first_name
        reg.lastname = request.user.last_name
        reg.created = timezone.now()
        reg.regtoken = generate_random_token()
        reg.idtoken = generate_random_token()
        reg.publictoken = generate_random_token()

    is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()

    if not is_active:
        # Registration not open.
        if reg.payconfirmedat:
            # Attendee has a completed registration, but registration is closed.
            # Render the dashboard.
            return _registration_dashboard(request, conference, reg, has_other_multiregs, redir_root)
        else:
            if today_conference() < conference.startdate:
                return render_conference_response(request, conference, 'reg', 'confreg/not_yet_open.html')
            else:
                return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

    # Else registration is open.

    if reg.invoice and not reg.payconfirmedat:
        # Pending invoice exists. See if it should be canceled.
        if reg.invoice.canceltime and reg.invoice.canceltime < timezone.now():
            # Yup, should be canceled
            manager = InvoiceManager()
            manager.cancel_invoice(reg.invoice,
                                   "Invoice was automatically canceled because payment was not received on time.",
                                   "system")

            # cancel_invoice will call the processor to unlink the invoice,
            # so make sure we refresh the object.
            reg = ConferenceRegistration.objects.get(id=reg.id)

    form_is_saved = False
    if request.method == 'POST':
        # Attempting to modify the registration
        if reg.bulkpayment:
            return render_conference_response(request, conference, 'reg', 'confreg/bulkpayexists.html')
        if reg.invoice:
            return render_conference_response(request, conference, 'reg', 'confreg/invoiceexists.html')

        # Did the user click cancel? We want to check that before we
        # check form.is_valid(), to avoid the user getting errors like
        # "you must specify country in order to cancel".
        # (This is submitted as a separate form in order to avoid client-side
        # versions of the same problem)
        if request.POST['submit'] == 'Cancel registration':
            if reg.id:
                reg.delete()
            return HttpResponseRedirect("{0}canceled/".format(redir_root))

        form = ConferenceRegistrationForm(request.user, data=request.POST, instance=reg)
        if form.is_valid():
            reg = form.save(commit=False)
            reg.conference = conference
            reg.attendee = request.user
            reg.registrator = request.user
            reg.save()
            form.save_m2m()
            form_is_saved = True

            # Figure out if the user clicked a "magic save button"
            if request.POST['submit'] == 'Confirm and finish' or request.POST['submit'] == 'Save and finish':
                reglog(reg, "Saved and clicked finish", request.user)
                # Complete registration!
                return HttpResponseRedirect("{0}confirm/".format(redir_root))

            reglog(reg, "Saved regform", request.user)

            # Or did they save but we're on the "wrong" url
            if redir_root:
                return HttpResponseRedirect(redir_root)

            # Else it was a general save, and we'll fall through and
            # show the form again so details can be edited.
    else:
        # This is just a get. Depending on the state of the registration,
        # we may want to show the form or not.
        if reg.payconfirmedat:
            # This registration is completed. Show the dashboard instead of
            # the registration form.
            return _registration_dashboard(request, conference, reg, has_other_multiregs, redir_root)

        if reg.invoice or reg.bulkpayment:
            # Invoice generated or part of bulk payment means the registration
            # can't be changed any more (without having someone cancel the
            # invoice).

            return render_conference_response(request, conference, 'reg', 'confreg/regform_completed.html', {
                'reg': reg,
                'redir_root': redir_root,
                'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/%s/register/" % (settings.SITEBASE, conference.urlname)),
            })

        # Else fall through and render the form
        form = ConferenceRegistrationForm(request.user, instance=reg)

    return render_conference_response(request, conference, 'reg', 'confreg/regform.html', {
        'form': form,
        'form_is_saved': form_is_saved,
        'reg': reg,
        'redir_root': redir_root,
        'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/%s/register/" % (settings.SITEBASE, conference.urlname)),
        'additionaloptions': conference.conferenceadditionaloption_set.filter(public=True),
        'costamount': reg.regtype and reg.regtype.cost or 0,
    })


@login_required
@transaction.atomic
def changereg(request, confname):
    # Change certain allowed fields on a registration.
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

    return _registration_dashboard(request, conference, reg, False, '../')


@login_required
@transaction.atomic
def reg_config_messaging(request, confname):
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user, payconfirmedat__isnull=False)

    if request.method != 'POST':
        raise Http404()

    if request.POST.get('op', None) == 'deactivate':
        reg.messaging = None
        reg.messaging_copiedfrom = None
        reg.messaging_config = {}
    else:
        # Else we're at the setup one
        reg.messaging = get_object_or_404(ConferenceMessaging, Q(id=request.POST['messagingid'], conference=conference) & (Q(privatebcast=True) | Q(notification=True)))
        reg.messaging_copiedfrom = None
        reg.messaging_config = {}

    reg.save(update_fields=['messaging', 'messaging_copiedfrom', 'messaging_config'])

    return HttpResponseRedirect('../#notifications')


@login_required
@transaction.atomic
def multireg(request, confname, regid=None):
    # "Register for somebody else" functionality.
    conference = get_conference_or_404(confname)
    is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()
    if not is_active:
        # Registration not open.
        if today_conference() < conference.startdate:
            return render_conference_response(request, conference, 'reg', 'confreg/not_yet_open.html')
        else:
            return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

    allregs = ConferenceRegistration.objects.filter(conference=conference, registrator=request.user)
    try:
        next((a for a in allregs if not (a.payconfirmedat or a.bulkpayment)))
        haspending = True
    except StopIteration:
        haspending = False

    if regid:
        # Editing a specific registration
        regid = regid.rstrip('/')
        reg = get_object_or_404(ConferenceRegistration,
                                pk=regid,
                                conference=conference,
                                registrator=request.user)
        redir_root = '../'
    else:
        reg = ConferenceRegistration(conference=conference,
                                     registrator=request.user,
                                     created=timezone.now(),
                                     regtoken=generate_random_token(),
                                     idtoken=generate_random_token(),
                                     publictoken=generate_random_token(),
        )
        redir_root = './'

    if request.method == 'POST':
        if request.POST['submit'] == 'New registration':
            # New registration form
            newform = NewMultiRegForm(conference, data=request.POST)
            if newform.is_valid():
                # Create a registration form for the details, and render
                # a separate page for it.
                # Create a registration but don't save it until we have
                # details entered.
                reg.email = newform.cleaned_data['email'].lower()
                regform = ConferenceRegistrationForm(request.user, instance=reg, regforother=True)
                return render_conference_response(request, conference, 'reg', 'confreg/regmulti_form.html', {
                    'form': regform,
                    '_email': newform.cleaned_data['email'].lower(),
                })
        elif request.POST['submit'] == 'Cancel':
            return HttpResponseRedirect(redir_root)
        elif request.POST['submit'] == 'Delete':
            if reg.pk:
                # Only delete if it has a primary key. Not having a primary key means
                # it was never saved, so there is nothing to delete.
                reg.delete()
            return HttpResponseRedirect(redir_root)
        elif request.POST['submit'] == 'Save':
            reg.email = request.POST.get('_email', '').lower()
            regform = ConferenceRegistrationForm(request.user, data=request.POST, instance=reg, regforother=True)
            if regform.is_valid():
                reg = regform.save(commit=False)
                reg.conference = conference
                reg.registrator = request.user
                reg.attendee = None
                reg.save()
                regform.save_m2m()
                reglog(reg, "Saved multireg form", request.user)
                return HttpResponseRedirect(redir_root)
            else:
                return render_conference_response(request, conference, 'reg', 'confreg/regmulti_form.html', {
                    'form': regform,
                })
        else:
            return HttpResponse("Unknown button pressed")
            newform = None
    else:
        if regid:
            # Editing a specific registration
            reg = get_object_or_404(ConferenceRegistration,
                                    pk=regid,
                                    conference=conference,
                                    registrator=request.user)
            regform = ConferenceRegistrationForm(request.user, instance=reg, regforother=True)
            return render_conference_response(request, conference, 'reg', 'confreg/regmulti_form.html', {
                'form': regform,
            })
        else:
            # Root page, so just render the base form
            newform = NewMultiRegForm(conference)

    return render_conference_response(request, conference, 'reg', 'confreg/regmulti.html', {
        'newform': newform,
        'allregs': allregs,
        'haspending': haspending,
        'activewaitlist': conference.waitlist_active(),
        'bulkpayments': BulkPayment.objects.filter(conference=conference, user=request.user),
    })


def _create_and_assign_bulk_payment(user, conference, regs, invoicerows, recipient_name, recipient_address, send_mail):
    autocancel_hours = [conference.invoice_autocancel_hours, ]

    bp = BulkPayment()
    bp.user = user
    bp.conference = conference
    bp.numregs = len(regs)
    bp.save()

    for r in regs:
        r.bulkpayment = bp
        r.save()
        reglog(r, "Assigned to bulk payment {}".format(bp.id), user)

        autocancel_hours.append(r.regtype.invoice_autocancel_hours)
        autocancel_hours.extend([a.invoice_autocancel_hours for a in r.additionaloptions.filter(invoice_autocancel_hours__isnull=False)])

        if send_mail:
            # Also notify these registrants that they have been
            # added to the bulk payment.
            send_conference_mail(conference,
                                 r.email,
                                 "Your registration has been added to multi-registration payment",
                                 'confreg/mail/bulkpay_added.txt',
                                 {
                                     'conference': conference,
                                     'reg': r,
                                     'bulk': bp,
                                 },
                                 receivername=r.fullname,
            )

    # Now that our bulkpayment is complete, create an invoice for it
    manager = InvoiceManager()
    processor = InvoiceProcessor.objects.get(processorname="confreg bulk processor")

    if bp.numregs > 1:
        invoicetitle = '%s multiple registrations' % conference.conferencename
    else:
        invoicetitle = "%s registration" % conference.conferencename
    bp.invoice = manager.create_invoice(
        user,
        user.email,
        recipient_name,
        recipient_address,
        invoicetitle,
        timezone.now(),
        timezone.now(),
        invoicerows,
        processor=processor,
        processorid=bp.pk,
        accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
        accounting_object=conference.accounting_object,
        canceltime=get_invoice_autocancel(*autocancel_hours),
        paymentmethods=conference.paymentmethods.all(),
    )
    bp.invoice.save()
    bp.save()

    return bp


@login_required
@transaction.atomic
def multireg_newinvoice(request, confname):
    conference = get_conference_or_404(confname)
    is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()
    if not is_active:
        # Registration not open.
        if today_conference() < conference.startdate:
            return render_conference_response(request, conference, 'reg', 'confreg/not_yet_open.html')
        else:
            return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

    if request.method == 'POST' and request.POST['submit'] == 'Cancel':
        return HttpResponseRedirect('../')

    # Collect all pending regs
    pendingregs = ConferenceRegistration.objects.filter(conference=conference,
                                                        registrator=request.user,
                                                        payconfirmedat__isnull=True,
                                                        invoice__isnull=True,
                                                        bulkpayment__isnull=True)
    if not pendingregs.exists():
        # No pending registrations exist, so just send back (should not
        # happen scenario)
        return HttpResponseRedirect('../')

    finalize = (request.method == 'POST' and request.POST['submit'] == 'Create')
    if finalize:
        savepoint = transaction.savepoint()

    # Almost like a bulk invoice, but we know the registrations were
    # created so they exist.
    errors = []
    invoicerows = []
    for r in pendingregs:
        if not r.regtype:
            errors.append('{0} has no registration type specified'.format(r.email))
        elif not r.regtype.active:
            errors.append('{0} uses registration type {1} which is not active'.format(r.email, r.regtype))
        elif r.regtype.activeuntil and r.regtype.activeuntil < today_conference():
            errors.append('{0} uses registration type {1} which is not active'.format(r.email, r.regtype))
        else:
            try:
                invoicerows.extend(invoicerows_for_registration(r, finalize))
            except InvoicerowsException as ex:
                errors.append('{0}: {1}'.format(r.email, ex))

    for r in invoicerows:
        # Calculate the with-vat information for this row
        if r[3]:
            r.append(r[2] * (100 + r[3].vatpercent) / Decimal(100))
        else:
            r.append(r[2])
    totalcost = sum([r[2] for r in invoicerows])
    totalwithvat = sum([r[4] for r in invoicerows])

    if finalize:
        form = MultiRegInvoiceForm(data=request.POST)
        if totalwithvat != Decimal(request.POST['totalwithvat']):
            errors.append('Total amount has changed, likely due to a registration being concurrently changed. Please try again.')
            # Error set, so will fall through into the path that rolls back

        if form.is_valid() and not errors:
            if totalwithvat == 0:
                errors.append('Should never happen, invoice should have already been bypassed for zero')
                # Fall through to render with errors
            else:
                # Else generate a bulk payment and invoice for it
                bp = _create_and_assign_bulk_payment(request.user,
                                                     conference,
                                                     pendingregs,
                                                     invoicerows,
                                                     form.data['recipient'],
                                                     form.data['address'],
                                                     False)

                return HttpResponseRedirect("../b{0}/".format(bp.id))

        # If we flagged discount codes etc as used, but came down her in the error path,
        # make sure we roll back the change.
        transaction.savepoint_rollback(savepoint)

        # Add the errors to the form, so they're actually visible.
        for e in errors:
            form.add_error(None, e)
    else:
        # No need to show the form in case we actually have a total cost of zero.
        # Instead, just immediately flag them as used.
        if totalwithvat == 0 and not errors:
            for r in pendingregs:
                # Flag discount code/vouchers as used
                invoicerows_for_registration(r, True)
                # Now mark the registration as done.
                r.payconfirmedat = timezone.now()
                r.payconfirmedby = "Multireg/nopay"
                r.save()
                reglog(r, "Confirmed by multireg not requiring payment", request.user)
                notify_reg_confirmed(r)
            return HttpResponseRedirect("../z/")

        form = MultiRegInvoiceForm()

    return render_conference_response(request, conference, 'reg', 'confreg/regmulti_invoice.html', {
        'form': form,
        'invoicerows': invoicerows,
        'totalcost': totalcost,
        'totalwithvat': totalwithvat,
    })


@login_required
def multireg_zeropay(request, confname):
    conference = get_conference_or_404(confname)
    return render_conference_response(request, conference, 'reg', 'confreg/regmulti_zeropay.html', {
    })


@login_required
@transaction.atomic
def multireg_bulkview(request, confname, bulkid):
    conference = get_conference_or_404(confname)
    is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()
    if not is_active:
        # Registration not open.
        if today_conference() < conference.startdate:
            return render_conference_response(request, conference, 'reg', 'confreg/not_yet_open.html')
        else:
            return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

    bp = get_object_or_404(BulkPayment, conference=conference, pk=bulkid, user=request.user)

    return render_conference_response(request, conference, 'reg', 'confreg/regmulti_bulk.html', {
        'bulkpayment': bp,
        'invoice': InvoicePresentationWrapper(bp.invoice, '.'),
    })


@login_required
@transaction.atomic
def multireg_bulk_cancel(request, confname, bulkid):
    conference = get_conference_or_404(confname)
    bp = get_object_or_404(BulkPayment, conference=conference, pk=bulkid, user=request.user)

    if not bp.invoice:
        return HttpResponseRedirect("../")
    if bp.invoice.paidat or bp.invoice.deleted:
        return HttpResponseRedirect("../")

    if request.method == 'POST':
        if request.POST['submit'].find('Cancel invoice') >= 0:
            manager = InvoiceManager()
            manager.cancel_invoice(bp.invoice, "User {0} requested cancellation".format(request.user), request.user.username)
            return HttpResponseRedirect('../../')
        else:
            return HttpResponseRedirect('../')

    return render_conference_response(request, conference, 'reg', 'confreg/regmulti_cancel.html', {
        'bp': bp,
    })


@login_required
@transaction.atomic
def multireg_attach(request, token):
    reg = get_object_or_404(ConferenceRegistration, regtoken=token)
    if reg.attendee:
        return HttpResponse("This registration has already been attached to an account")

    conference = reg.conference
    if ConferenceRegistration.objects.filter(conference=conference, attendee=request.user).exists():
        return HttpResponse("Logged in user ({0}) already has a registration at this conference".format(request.user.username))

    # Else we ask the user to confirm
    if request.method == "POST" and request.POST['submit'] == 'Confirm and attach account':
        reg.attendee = request.user
        reg.save()
        reglog(reg, "Attached registration to account", request.user)
        return HttpResponseRedirect('/events/register/{0}/'.format(conference.urlname))
    else:
        return render_conference_response(request, conference, 'reg', 'confreg/regmulti_attach.html', {
            'reg': reg,
        })


def feedback_available(request):
    conferences = Conference.objects.filter(feedbackopen=True).order_by('startdate')
    return render(request, 'confreg/feedback_available.html', {
        'conferences': conferences,
    })


@login_required
@transaction.atomic
def reg_add_options(request, confname):
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

    if not reg.payconfirmedat:
        messages.warning(request, "Registration not confirmed, should not get here")
        return HttpResponseRedirect('../')

    if reg.canceledat:
        messages.warning(request, "Registration canceled, should not get here")
        return HttpResponseRedirect('../')

    if request.POST.get('submit', '') == 'Back':
        return HttpResponseRedirect('../')

    options = []
    for k, v in list(request.POST.items()):
        if k.startswith('ao_') and v == "1":
            options.append(int(k[3:]))

    if not len(options) > 0:
        messages.info(request, "No additional options selected, nothing to order")
        return HttpResponseRedirect('../')

    options = ConferenceAdditionalOption.objects.filter(conference=conference, pk__in=options, upsellable=True)
    if len(options) < 0:
        messages.warning(request, "Option searching mismatch, order canceled.")
        return HttpResponseRedirect('../')

    # Check the count on each option (yes, this is inefficient, but who cares)
    for o in options:
        if o.maxcount > 0:
            if o.conferenceregistration_set.count() + o.pendingadditionalorder_set.filter(payconfirmedat__isnull=True).count() >= o.maxcount:
                messages.warning(request, "Option '{0}' is sold out.".format(o.name))
                return HttpResponseRedirect('../')

    # Check if any of the options are mutually exclusive
    for o in options:
        for x in o.mutually_exclusive.all():
            if x in options:
                messages.warning(request, "Option '{0}' can't be ordered at the same time as '{1}'".format(o.name, x.name))
                return HttpResponseRedirect('../')

    # Check if any of the options require a different regtype,
    # and that this regtype is upsellable.
    new_regtype = None
    for o in options:
        a = o.requires_regtype.all()
        if a and reg.regtype not in a:
            # New regtype is required. Figure out if there is an upsellable
            # one available.
            upsellable = o.requires_regtype.filter(Q(upsell_target=True, active=True, specialtype__isnull=True) & (Q(activeuntil__isnull=True) | Q(activeuntil__lt=today_conference())))
            num = len(upsellable)
            if num == 0:
                messages.warning(request, "Option {0} requires a registration type that's not available.".format(o.name))
                return HttpResponseRedirect('../')
            elif num > 1:
                messages.warning(request, "Option {0} requires a registration type that cannot be automaticalliy selected. Please email the organizers to make your registration.".format(o.name))
                return HttpResponseRedirect('../')
            if new_regtype:
                # A new registration type has been selected by another option
                # so we need to verify if it's the same.
                if new_regtype != upsellable[0]:
                    messages.warning(request, "Requested options require different registration types, and cannot be ordered.")
                    return HttpResponseRedirect('../')
            else:
                new_regtype = upsellable[0]

    if new_regtype and new_regtype.cost >= reg.regtype.cost:
        upsell_cost = new_regtype.cost - reg.regtype.cost
    else:
        upsell_cost = 0

    # Build our invoice rows
    invoicerows = []
    autocancel_hours = [conference.invoice_autocancel_hours, ]
    if upsell_cost:
        invoicerows.append(['Upgrade to {0}'.format(new_regtype.regtype), 1, upsell_cost, conference.vat_registrations])
        if new_regtype.invoice_autocancel_hours:
            autocancel_hours.append(new_regtype.invoice_autocancel_hours)

    for o in options:
        # Yes, we include €0 options for completeness.
        invoicerows.append([o.name, 1, o.cost, conference.vat_registrations])
        if o.invoice_autocancel_hours:
            autocancel_hours.append(o.invoice_autocancel_hours)

    # Add VAT information to invoice rows
    for r in invoicerows:
        # Calculate the with-vat information for this row
        if r[3]:
            r.append(r[2] * (100 + r[3].vatpercent) / Decimal(100))
        else:
            r.append(r[2])

    totalcost = sum([r[2] for r in invoicerows])
    totalwithvat = sum([r[4] for r in invoicerows])

    if not request.POST.get('confirm', None) == 'yes':
        # Generate a preview
        return render_conference_response(request, conference, 'reg', 'confreg/confirm_addons.html', {
            'reg': reg,
            'options': options,
            'invoicerows': invoicerows,
            'totalcost': totalcost,
            'totalwithvat': totalwithvat,
        })
    else:
        if totalcost == 0:
            # No payment, but possibly update the registration type, and
            # definitely add the option.
            if new_regtype:
                reg.regtype = new_regtype
            for o in options:
                reg.additionaloptions.add(o)
            reg.save()
            reglog(reg, "Added additional options (no payment needed)", request.user)
            messages.info(request, 'Additional options added to registration')
            return HttpResponseRedirect('../')

        # Create a pending addon order, and generate an invoice
        order = PendingAdditionalOrder(reg=reg,
                                       createtime=timezone.now())
        if new_regtype:
            order.newregtype = new_regtype

        order.save()  # So we get a PK and can add m2m values
        for o in options:
            order.options.add(o)

        reglog(reg, "Created additional options order {}".format(order.id), request.user)

        manager = InvoiceManager()
        processor = InvoiceProcessor.objects.get(processorname='confreg addon processor')
        order.invoice = manager.create_invoice(
            request.user,
            request.user.email,
            reg.firstname + ' ' + reg.lastname,
            reg.company + "\n" + reg.address + "\n" + reg.countryname,
            "%s additional options" % conference.conferencename,
            timezone.now(),
            timezone.now(),
            invoicerows,
            processor=processor,
            processorid=order.pk,
            accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
            accounting_object=conference.accounting_object,
            canceltime=get_invoice_autocancel(*autocancel_hours),
            paymentmethods=conference.paymentmethods.all(),
        )
        order.invoice.save()
        order.save()

        # Redirect the user to the invoice
        return HttpResponseRedirect('/invoices/{0}/{1}/'.format(order.invoice.id, order.invoice.recipient_secret))


@login_required
def feedback(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.feedbackopen:
        # Allow conference testers to override
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'feedback', 'confreg/feedbackclosed.html')
        else:
            is_conf_tester = True
    else:
        is_conf_tester = False

    # Figure out if the user is registered
    try:
        r = ConferenceRegistration.objects.get(conference=conference, attendee=request.user)
    except ConferenceRegistration.DoesNotExist:
        return HttpResponse('You are not registered for this conference.')

    if not r.payconfirmedat:
        if r.regtype.cost != 0:
            return HttpResponse('You are not a confirmed attendee of this conference.')

    if r.canceledat:
        return HttpResponse("Your registration has been canceled.")

    # Generate a list of all feedback:able sessions, meaning all sessions that have already started,
    # since you can't give feedback on something that does not yet exist.
    if is_conf_tester:
        sessions = ConferenceSession.objects.select_related().filter(conference=conference).filter(can_feedback=True).filter(status=1)
    else:
        sessions = ConferenceSession.objects.select_related().filter(conference=conference).filter(can_feedback=True).filter(starttime__lte=timezone.now()).filter(status=1)

    # Then get a list of everything this user has feedbacked on
    feedback = ConferenceSessionFeedback.objects.filter(conference=conference, attendee=request.user)

    # Since we can't trick django to do a LEFT JOIN for us here, implement that part
    # in code here. The number of sessions is always going to be low, so it won't
    # be too big a performance issue.
    for s in sessions:
        fb = [f for f in feedback if f.session == s]
        if len(fb):
            s.has_given_feedback = True

    return render_conference_response(request, conference, 'feedback', 'confreg/feedback_index.html', {
        'sessions': sessions,
        'is_tester': is_conf_tester,
    })


@login_required
def feedback_session(request, confname, sessionid):
    # Room for optimization: don't get these as separate steps
    conference = get_conference_or_404(confname)
    session = get_object_or_404(ConferenceSession, pk=sessionid, conference=conference, status=1)

    if not conference.feedbackopen:
        # Allow conference testers to override
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'feedback', 'confreg/feedbackclosed.html')
        else:
            is_conf_tester = True
    else:
        is_conf_tester = False

    if session.starttime > timezone.now() and not is_conf_tester:
        return render_conference_response(request, conference, 'feedback', 'confreg/feedbacknotyet.html', {
            'session': session,
        })

    try:
        feedback = ConferenceSessionFeedback.objects.get(conference=conference, session=session, attendee=request.user)
    except ConferenceSessionFeedback.DoesNotExist:
        feedback = ConferenceSessionFeedback()

    if request.method == 'POST':
        form = ConferenceSessionFeedbackForm(data=request.POST, instance=feedback)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.conference = conference
            feedback.attendee = request.user
            feedback.session = session
            feedback.save()
            return HttpResponseRedirect('..')
    else:
        form = ConferenceSessionFeedbackForm(instance=feedback)

    return render_conference_response(request, conference, 'feedback', 'confreg/feedback.html', {
        'session': session,
        'form': form,
    })


@login_required
@transaction.atomic
def feedback_conference(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.feedbackopen:
        # Allow conference testers to override
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'feedback', 'confreg/feedbackclosed.html')

    # Get all questions
    questions = ConferenceFeedbackQuestion.objects.filter(conference=conference)

    # Get all current responses
    responses = ConferenceFeedbackAnswer.objects.filter(conference=conference, attendee=request.user)

    if request.method == 'POST':
        form = ConferenceFeedbackForm(data=request.POST, questions=questions, responses=responses)
        if form.is_valid():
            # We've got the data, now write it to the database.
            for q in questions:
                a, created = ConferenceFeedbackAnswer.objects.get_or_create(conference=conference, question=q, attendee=request.user)
                if q.isfreetext:
                    a.textanswer = form.cleaned_data['question_%s' % q.id]
                else:
                    a.rateanswer = form.cleaned_data['question_%s' % q.id]
                a.save()
            return HttpResponseRedirect('..')
    else:
        form = ConferenceFeedbackForm(questions=questions, responses=responses)

    return render_conference_response(request, conference, 'feedback', 'confreg/feedback_conference.html', {
        'session': session,
        'form': form,
    })


class SessionSet(object):
    def __init__(self, allrooms, day_rooms, totalwidth, pixelsperminute, feedbackopen, sessions):
        self.headersize = 30
        self.available_rooms = allrooms
        self.totalwidth = totalwidth
        self.pixelsperminute = pixelsperminute
        self.feedbackopen = feedbackopen

        # Get a dict from each roomid to the 0-based position of the room from left to right,
        # so the position can be calculated.
        self.rooms = dict(list(zip(day_rooms, list(range(len(day_rooms))))))

        # Populate the dict for all sessions
        self.sessions = [self._session_template_dict(s) for s in sessions if s['room_id'] or s['cross_schedule']]

    def _session_template_dict(self, s):
        # For old-style rendering, update positions
        if not s['cross_schedule']:
            s.update({
                'leftpos': self.roomwidth() * self.rooms[s['room_id']],
                'toppos': self.timediff_to_y_pixels(s['starttime'], s['firsttime']) + self.headersize,
                'widthpos': self.roomwidth() - 2,
                'heightpos': self.timediff_to_y_pixels(s['endtime'], s['starttime']),
                'canfeedback': self.feedbackopen and s.get('can_feedback', False) and (s['starttime'] <= timezone.now()),
            })
        else:
            s.update({
                'leftpos': 0,
                'toppos': self.timediff_to_y_pixels(s['starttime'], s['firsttime']) + self.headersize,
                'widthpos': self.roomwidth() * len(self.rooms) - 2,
                'heightpos': self.timediff_to_y_pixels(s['endtime'], s['starttime']) - 2,
                'canfeedback': False,
            })
            if 'id' in s:
                del s['id']
        # Remove raw can_feedback value, we have replaced it with canfeedback that's calculated
        if 'can_feedback' in s:
            del s['can_feedback']
        return s

    def all(self):
        return self.sessions

    def schedule_height(self):
        return self.timediff_to_y_pixels(self.sessions[0]['lasttime'], self.sessions[0]['firsttime']) + 2 + self.headersize

    def schedule_width(self):
        if len(self.rooms):
            return self.roomwidth() * len(self.rooms)
        else:
            return 0

    def roomwidth(self):
        if len(self.rooms):
            return int(self.totalwidth // len(self.rooms))
        else:
            return 0

    def timediff_to_y_pixels(self, t, compareto):
        return ((t - compareto).seconds // 60) * self.pixelsperminute

    def allrooms(self):
        return [{
            'id': id,
            'name': self.available_rooms[id]['roomname'],
            'url': self.available_rooms[id]['url'],
            'comment': self.available_rooms[id]['roomcomment'],
            'leftpos': self.roomwidth() * self.rooms[id],
            'widthpos': self.roomwidth() - 2,
            'heightpos': self.headersize - 2,
            'sessions': list(self.room_sessions(id)),
        } for id, idx in sorted(list(self.rooms.items()), key=lambda x: x[1])]

    def room_sessions(self, roomid):
        roomprevsess = None
        for s in self.sessions:
            if s['cross_schedule'] or s['room_id'] == roomid:
                if roomprevsess and roomprevsess['endtime'] < s['starttime']:
                    yield {'empty': True,
                           'length': (s['starttime'] - roomprevsess['endtime']).total_seconds() // 60,
                    }
                roomprevsess = s
                yield s


def _scheduledata(request, conference):
    with ensure_conference_timezone(conference):
        tracks = exec_to_dict("SELECT id, color, fgcolor, incfp, trackname, sortkey, showcompany FROM confreg_track t WHERE conference_id=%(confid)s AND EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.track_id=t.id AND s.status=1) ORDER BY sortkey", {
            'confid': conference.id,
        })

        allrooms = exec_to_keyed_dict("SELECT id, sortkey, url, roomname, comment AS roomcomment FROM confreg_room r WHERE conference_id=%(confid)s", {
            'confid': conference.id,
        })

        day_rooms = exec_to_keyed_dict("""WITH t AS (
  SELECT s.starttime::date AS day, room_id
   FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND status=1 AND s.room_id IS NOT NULL AND s.starttime IS NOT NULL
 UNION
  SELECT d.day, ad.room_id
   FROM confreg_room_availabledays ad INNER JOIN confreg_registrationday d ON d.id=ad.registrationday_id
)
SELECT day, array_agg(room_id ORDER BY r.sortkey, r.roomname) AS rooms FROM t
INNER JOIN confreg_room r ON r.id=t.room_id GROUP BY day
""", {
            'confid': conference.id,
        })

        raw = exec_to_grouped_dict("""SELECT
    s.starttime::date AS day,
    s.id, s.starttime,
    s.endtime,
    s.can_feedback,
    to_json(t.*) AS track,
    s.track_id,
    to_json(r.*) AS room,
    s.room_id,
    s.title,
    s.htmlicon,
    to_char(starttime, 'HH24:MI') || ' - ' || to_char(endtime, 'HH24:MI') AS timeslot,
    extract(epoch FROM endtime-starttime)/60 AS length, min(starttime) OVER days AS firsttime,
    max(endtime) OVER days AS lasttime, cross_schedule,
    EXISTS (SELECT 1 FROM confreg_conferencesessionslides sl WHERE sl.session_id=s.id) AS has_slides,
    COALESCE(json_agg(json_build_object(
       'id', spk.id,
       'name', spk.fullname,
       'company', spk.company,
       'twittername', spk.twittername
    ) ORDER BY spk.fullname) FILTER (WHERE spk.id IS NOT NULL), '[]') AS speakers
FROM confreg_conferencesession s
LEFT JOIN confreg_track t ON t.id=s.track_id
LEFT JOIN confreg_room r ON r.id=s.room_id
LEFT JOIN confreg_conferencesession_speaker css ON css.conferencesession_id=s.id
LEFT JOIN confreg_speaker spk ON spk.id=css.speaker_id
WHERE
    s.conference_id=%(confid)s AND
    s.status=1
    AND (cross_schedule OR room_id IS NOT NULL)
GROUP BY s.id, t.id, r.id
WINDOW days AS (PARTITION BY s.starttime::date)
ORDER BY day, s.starttime, r.sortkey""", {
            'confid': conference.id,
        })

    days = []
    roomsinuse = set()
    for d, sessions in list(raw.items()):
        if d not in day_rooms:
            # This day has no rooms. This can happen if *all* sessions for the day are cross-schedule.
            # It cannot happen if there are no sessions at all, because then they simply wouldn't
            # be included in the raw result.
            # For now, just ignore days that have only cross-schedule entries, to avoid crashing.
            continue
        roomsinuse |= set(day_rooms[d]['rooms'])

        sessionset = SessionSet(allrooms, day_rooms[d]['rooms'],
                                conference.schedulewidth, conference.pixelsperminute,
                                conference.feedbackopen,
                                sessions)
        days.append({
            'day': d,
            'sessions': list(sessionset.all()),
            'rooms': sessionset.allrooms(),
            'schedule_height': sessionset.schedule_height(),
            'schedule_width': sessionset.schedule_width(),
        })

    return {
        'days': days,
        'tracks': tracks,
        'rooms': sorted([allrooms[r] for r in roomsinuse], key=lambda x: (x['sortkey'], x['roomname']))
    }


def schedule(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.scheduleactive:
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'schedule', 'confreg/scheduleclosed.html')

    return render_conference_response(request, conference, 'schedule', 'confreg/schedule.html', _scheduledata(request, conference))


def schedulejson(request, confname):
    conference = get_authenticated_conference(request, confname)

    return HttpResponse(json.dumps(_scheduledata(request, conference),
                                   cls=JsonSerializer,
                                   indent=2),
                        content_type='application/json')


def sessionlist(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.sessionsactive:
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'sessions', 'confreg/sessionsclosed.html')

    sessions = ConferenceSession.objects.filter(conference=conference).extra(select={
        'has_slides': 'EXISTS (SELECT 1 FROM confreg_conferencesessionslides WHERE session_id=confreg_conferencesession.id)',
    }).filter(cross_schedule=False).filter(status=1).order_by('track__sortkey', 'track', 'title')

    return render_conference_response(request, conference, 'sessions', 'confreg/sessionlist.html', {
        'sessions': sessions,
    })


def schedule_ical(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.scheduleactive:
        # Not open. But we can't really render an error, so render a
        # completely empty session list instead
        sessions = None
    else:
        sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).filter(starttime__isnull=False).order_by('starttime')
    resp = render(request, 'confreg/schedule.ical', {
        'conference': conference,
        'sessions': sessions,
    }, content_type='text/calendar')
    resp['Content-Disposition'] = 'attachment; filename="{}.ical"'.format(conference.urlname)
    return resp


def schedule_xcal(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.scheduleactive:
        raise Http404()
    x = ET.Element('iCalendar')
    v = ET.SubElement(x, 'vcalendar')
    ET.SubElement(v, 'version').text = '2.0'
    ET.SubElement(v, 'prodid').text = '//pgeusys//Schedule 1.0//EN'
    ET.SubElement(v, 'x-wr-caldesc')
    ET.SubElement(v, 'x-wr-calname').text = 'Schedule for {0}'.format(conference.conferencename)
    for sess in ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).filter(starttime__isnull=False).order_by('starttime'):
        s = ET.SubElement(v, 'vevent')
        ET.SubElement(s, 'method').text = 'PUBLISH'
        ET.SubElement(s, 'uid').text = '{0}@{1}'.format(sess.id, conference.urlname)
        ET.SubElement(s, 'dtstart').text = sess.starttime.strftime('%Y%m%dT%H%M%SZ')
        ET.SubElement(s, 'dtend').text = sess.endtime.strftime('%Y%m%dT%H%M%SZ')
        ET.SubElement(s, 'summary').text = sess.title
        ET.SubElement(s, 'description').text = sess.abstract
        ET.SubElement(s, 'class').text = 'PUBLIC'
        ET.SubElement(s, 'status').text = 'CONFIRMED'
        ET.SubElement(s, 'url').text = '{0}/events/{1}/schedule/session/{2}/'.format(settings.SITEBASE, conference.urlname, sess.id)
        ET.SubElement(s, 'location').text = sess.room and sess.room.roomname or ''
        for spk in sess.speaker.all():
            ET.SubElement(s, 'attendee').text = spk.name
    resp = HttpResponse(content_type='text/xml; charset=utf-8')
    ET.ElementTree(x).write(resp, encoding='utf-8', xml_declaration=True)
    resp['Content-Disposition'] = 'attachment; filename="{}.xcs"'.format(conference.urlname)
    return resp


def _timedelta_minutes(td):
    hours, remainder = divmod(td.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return "{:02}:{:02}".format(int(hours), int(minutes))


def schedule_xml(request, confname):
    conference = get_conference_or_404(confname)

    if not conference.scheduleactive:
        raise Http404()
    x = ET.Element('schedule')
    ET.SubElement(x, 'version').text = 'Firefly'
    c = ET.SubElement(x, 'conference')
    ET.SubElement(c, 'title').text = conference.conferencename
    ET.SubElement(c, 'start').text = conference.startdate.strftime("%Y-%m-%d")
    ET.SubElement(c, 'end').text = conference.enddate.strftime("%Y-%m-%d")
    ET.SubElement(c, 'days').text = str((conference.enddate - conference.startdate).days + 1)
    ET.SubElement(c, 'baseurl').text = '{0}/events/{1}/schedule/'.format(settings.SITEBASE, conference.urlname)

    lastday = None
    lastroom = None
    for sess in ConferenceSession.objects.filter(conference=conference).filter(status=1).filter(starttime__isnull=False).order_by('starttime', 'cross_schedule', 'room__sortkey'):
        if lastday != timezone.localdate(sess.starttime):
            lastday = timezone.localdate(sess.starttime)
            lastroom = None
            xday = ET.SubElement(x, 'day', date=lastday.strftime("%Y-%m-%d"))  # START/END!
        thisroom = sess.cross_schedule and 'Other' or sess.room.roomname
        if lastroom != thisroom:
            lastroom = thisroom
            xroom = ET.SubElement(xday, 'room', name=lastroom)
        e = ET.SubElement(xroom, 'event', id=str(sess.id))
        ET.SubElement(e, 'start').text = timezone.localtime(sess.starttime).strftime('%H:%M')
        ET.SubElement(e, 'duration').text = _timedelta_minutes(sess.endtime - sess.starttime)
        ET.SubElement(e, 'room').text = lastroom
        ET.SubElement(e, 'title').text = sess.title
        ET.SubElement(e, 'abstract').text = sess.abstract
        ET.SubElement(e, 'url').text = '{0}/events/{1}/schedule/session/{2}/'.format(settings.SITEBASE, conference.urlname, sess.id)
        if sess.track:
            ET.SubElement(e, 'track').text = sess.track.trackname
        p = ET.SubElement(e, 'persons')
        for spk in sess.speaker.all():
            ET.SubElement(p, 'person', id=str(spk.id)).text = spk.name

    resp = HttpResponse(content_type='text/xml; charset=utf-8')
    ET.ElementTree(x).write(resp, encoding='utf-8', xml_declaration=True)
    resp['Content-Disposition'] = 'attachment; filename="{}.xml"'.format(conference.urlname)
    return resp


def session(request, confname, sessionid):
    conference = get_conference_or_404(confname)

    if not conference.sessionsactive:
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'schedule', 'confreg/sessionsclosed.html')

    session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
    return render_conference_response(request, conference, 'schedule', 'confreg/session.html', {
        'session': session,
        'slides': ConferenceSessionSlides.objects.filter(session=session),
    })


def session_card(request, confname, sessionid, cardformat):
    conference = get_conference_or_404(confname)

    if not (conference.sessionsactive and conference.cardsactive):
        if not conference.testers.filter(pk=request.user.id):
            raise HttpResponseForbidden()

    session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
    return render_jinja_conference_svg(request, conference, cardformat, 'confreg/cards/session.svg', {
        'session': session,
    })


def session_slides(request, confname, sessionid, slideid):
    conference = get_conference_or_404(confname)

    if not conference.sessionsactive:
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'schedule', 'confreg/sessionsclosed.html')

    session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
    slides = get_object_or_404(ConferenceSessionSlides, session=session, id=slideid)
    return HttpResponse(bytes(slides.content),
                        content_type='application/pdf')


def speaker(request, confname, speakerid):
    conference = get_conference_or_404(confname)
    if not conference.sessionsactive:
        if not conference.testers.filter(pk=request.user.id):
            return render_conference_response(request, conference, 'schedule', 'confreg/sessionsclosed.html')

    speaker = get_object_or_404(Speaker, pk=speakerid)
    sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker, cross_schedule=False, status=1).order_by('starttime')
    if len(sessions) < 1:
        raise Http404("Speaker has no sessions at this conference")
    return render_conference_response(request, conference, 'schedule', 'confreg/speaker.html', {
        'speaker': speaker,
        'sessions': sessions,
    })


def speaker_card(request, confname, speakerid, cardformat):
    conference = get_conference_or_404(confname)

    if not (conference.sessionsactive and conference.cardsactive):
        if not conference.testers.filter(pk=request.user.id):
            return HttpResponseForbidden()

    speaker = get_object_or_404(Speaker, pk=speakerid)
    sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker, cross_schedule=False, status=1).order_by('starttime')
    if len(sessions) < 1:
        raise Http404("Speaker has no sessions at this conference")

    return render_jinja_conference_svg(request, conference, cardformat, 'confreg/cards/speaker.svg', {
        'speaker': speaker,
        'sessions': sessions,
    })


def speakerphoto(request, speakerid):
    speaker = get_object_or_404(Speaker, pk=speakerid)
    return HttpResponse(bytes(speaker.photo), content_type='image/jpg')


@login_required
def speakerprofile(request, confurlname=None):
    if confurlname:
        conf = get_conference_or_404(confurlname)
    else:
        conf = None

    speaker = conferences = callforpapers = None
    try:
        speaker = get_object_or_404(Speaker, user=request.user)
        conferences = Conference.objects.filter(conferencesession__speaker=speaker).distinct()
        callforpapers = Conference.objects.filter(callforpapersopen=True).order_by('startdate')
    except Speaker.DoesNotExist:
        speaker = None
        conferences = []
        callforpapers = None
    except Exception:
        pass

    if request.method == 'POST':
        # Attempt to save
        # If this is a new speaker, create an instance for it
        if not speaker:
            speaker = Speaker(user=request.user, fullname=request.user.first_name)
            speaker.speakertoken = generate_random_token()
            speaker.save()

        form = SpeakerProfileForm(data=request.POST, files=request.FILES, instance=speaker)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('.')
    else:
        form = SpeakerProfileForm(instance=speaker)

    return render_conference_response(request, conf, 'cfp', 'confreg/speakerprofile.html', {
        'speaker': speaker,
        'conferences': conferences,
        'callforpapers': callforpapers,
        'form': form,
    })


@login_required
@transaction.atomic
def callforpapers(request, confname):
    conference = get_conference_or_404(confname)
    # This is called both for open and non-open call for papers, to let submitters view
    # when the schedule is not published. Thus, no check for callforpapersopen here.

    is_tester = conference.testers.filter(pk=request.user.id).exists()

    try:
        speaker = Speaker.objects.get(user=request.user)
        sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker).order_by('title')
        other_submissions = ConferenceSession.objects.filter(speaker=speaker).exclude(conference=conference).exists()
    except Speaker.DoesNotExist:
        other_submissions = False
        sessions = []

    return render_conference_response(request, conference, 'cfp', 'confreg/callforpapers.html', {
        'other_submissions': other_submissions,
        'sessions': sessions,
        'is_tester': is_tester,
    })


@login_required
def callforpaperslist(request):
    speaker = callforpapers = None
    try:
        speaker = get_object_or_404(Speaker, user=request.user)
        callforpapers = Conference.objects.filter(callforpapersopen=True).order_by('startdate')
    except Speaker.DoesNotExist:
        speaker = None
        callforpapers = None
    except Exception:
        pass

    return render_conference_response(request, None, 'cfp', 'confreg/callforpaperslist.html', {
        'speaker': speaker,
        'callforpapers': callforpapers,
    })


@login_required
def callforpapers_edit(request, confname, sessionid):
    conference = get_conference_or_404(confname)
    is_tester = conference.testers.filter(pk=request.user.id).exists()

    if sessionid == 'new':
        if not (conference.callforpapersopen or is_tester):
            # Should never happen, so just redirect the user
            return HttpResponseRedirect("../")

        # Create speaker record if necessary
        speaker, created = Speaker.objects.get_or_create(user=request.user, defaults={
            'fullname': request.user.first_name,
            'speakertoken': generate_random_token(),
        })

        session = ConferenceSession(conference=conference, status=0, initialsubmit=timezone.now())
    else:
        # Find users speaker record (should always exist when we get this far)
        speaker = get_object_or_404(Speaker, user=request.user)

        # Find the session record (should always exist when we get this far)
        session = get_object_or_404(ConferenceSession, conference=conference,
                                    speaker=speaker, pk=sessionid)

    # If the user is a tester, it overrides the callforpapersopen check
    isopen = conference.callforpapersopen or is_tester
    if (isopen and session.status != 0) or not isopen:
        # Anything that's not "open and in status submitted" renders
        # a view of the session instead of the actual session.
        # If there is feedback for this session available, render that
        # on the same page. If feedback is  still open, we show nothing
        feedback_fields = ('topic_importance', 'content_quality', 'speaker_knowledge', 'speaker_quality')
        if is_tester or not conference.feedbackopen:
            feedbackdata = [{'key': k, 'title': k.replace('_', ' ').title(), 'num': [0] * 5} for k in feedback_fields]
            feedbacktext = []
            fb = list(ConferenceSessionFeedback.objects.filter(conference=conference, session=session))
            feedbackcount = len(fb)
            for f in fb:
                # Summarize the values
                for d in feedbackdata:
                    if getattr(f, d['key']) > 0:
                        d['num'][getattr(f, d['key']) - 1] += 1
                # Add the text if necessary
                if f.speaker_feedback:
                    feedbacktext.append({
                        'feedback': f.speaker_feedback,
                        'scores': [getattr(f, fn) for fn in feedback_fields],
                        })
            # Build the histogram data. For now, one query per measurement
            curs = connection.cursor()
            feedbackcomparisons = []
            for measurement in feedback_fields:
                curs.execute("SELECT g.g,g.g+0.25,COALESCE(y.count,0),this FROM generate_series(0,4.75,0.25) g(g) LEFT JOIN (SELECT r, count(*), max(this::int) AS this FROM (SELECT session_id,round(floor(avg({0})*4)/4,2) AS r,session_id=%(sessid)s AS this FROM confreg_conferencesessionfeedback WHERE conference_id=%(confid)s AND {0}>0 GROUP BY session_id) x GROUP BY r) y ON g.g=y.r".format(measurement), {
                    'confid': conference.id,
                    'sessid': session.id,
                })
                feedbackcomparisons.append({
                    'key': measurement,
                    'title': measurement.replace('_', ' ').title(),
                    'vals': curs.fetchall(),
                })
        else:
            feedbackcount = 0
            feedbackdata = None
            feedbacktext = None
            feedbackcomparisons = None

        # Slides slides slides!
        if request.method == 'POST':
            slidesurlform = SessionSlidesUrlForm(data=request.POST)
            slidesfileform = SessionSlidesFileForm(data=request.POST, files=request.FILES)
            if slidesurlform.is_valid() and slidesfileform.is_valid():
                # URL first!
                if slidesurlform.cleaned_data['url']:
                    ConferenceSessionSlides(session=session,
                                            name=slidesurlform.cleaned_data['url'][:100],
                                            url=slidesurlform.cleaned_data['url'],
                                            content=None).save()
                    return HttpResponseRedirect(".")
                elif request.FILES:
                    if len(request.FILES) != 1:
                        raise Exception("Only one file at a time, sorry!")
                    for k, v in list(request.FILES.items()):
                        ConferenceSessionSlides(session=session,
                                                name=v.name,
                                                content=v.read()).save()
                    return HttpResponseRedirect(".")
                else:
                    # No url, no file, so just re-render
                    pass
        else:
            slidesurlform = SessionSlidesUrlForm()
            slidesfileform = SessionSlidesFileForm()

        return render_conference_response(request, conference, 'cfp', 'confreg/session_feedback.html', {
            'session': session,
            'feedbackcount': feedbackcount,
            'feedbackdata': feedbackdata,
            'feedbacktext': feedbacktext,
            'feedbackcomparisons': feedbackcomparisons,
            'feedbackfields': [f.replace('_', ' ').title() for f in feedback_fields],
            'slidesurlform': slidesurlform,
            'slidesfileform': slidesfileform,
            'slides': ConferenceSessionSlides.objects.filter(session=session),
            })

    if session.id:
        initial = {}
    else:
        initial = {
            'speaker': [speaker, ],
        }

    if request.method == 'POST':
        # Save it!
        form = CallForPapersForm(speaker, data=request.POST, instance=session, initial=initial)
        if form.is_valid():
            form.save()

            messages.info(request, "Your session '%s' has been saved!" % session.title)
            return HttpResponseRedirect("../")
    else:
        # GET --> render empty form
        form = CallForPapersForm(speaker, instance=session, initial=initial)

    return render_conference_response(request, conference, 'cfp', 'confreg/callforpapersform.html', {
        'form': form,
        'session': session,
    })


@login_required
def public_speaker_lookup(request, confname):
    if 'query' not in request.GET:
        raise Http404("No query")

    conference = get_conference_or_404(confname)
    speaker = get_object_or_404(Speaker, user=request.user)

    # This is a lookup for speakers that's public. To avoid harvesting, we allow
    # only *prefix* matching of email addresses, and you have to type at least 6 characters
    # before you get anything.
    prefix = request.GET['query'].lower()
    if len(prefix) > 5:
        vals = [{
            'id': s.id,
            'value': "{0} <{1}>".format(s.fullname, s.email),
        } for s in Speaker.objects.filter(user__email__startswith=prefix).exclude(fullname='')]
    else:
        vals = []
    return HttpResponse(json.dumps({
        'values': vals,
    }), content_type='application/json')


@login_required
def public_tags_lookup(request, confname):
    if 'query' not in request.GET:
        raise Http404("No query")

    conference = get_conference_or_404(confname)
    speaker = get_object_or_404(Speaker, user=request.user)

    prefix = request.GET['query']
    vals = [{
        'id': t.id,
        'value': t.tag,
    } for t in ConferenceSessionTag.objects.filter(conference=conference)]
    return HttpResponse(json.dumps({
        'values': vals,
    }), content_type='application/json')


@login_required
@transaction.atomic
def callforpapers_copy(request, confname):
    conference = get_conference_or_404(confname)
    speaker = get_object_or_404(Speaker, user=request.user)

    if request.method == 'POST':
        form = CallForPapersCopyForm(conference, speaker, data=request.POST)
        if form.is_valid():
            for s in form.cleaned_data['sessions']:
                # The majority of all fields should just be blank in the new submission, so create
                # a new session object instead of trying to copy the old one.
                submissionnote = "Submission copied from {0}.".format(s.conference)
                if s.submissionnote:
                    submissionnote += " Original note:\n\n" + s.submissionnote

                n = ConferenceSession(conference=conference,
                                      title=s.title,
                                      abstract=s.abstract,
                                      skill_level=s.skill_level,
                                      status=0,
                                      initialsubmit=timezone.now(),
                                      submissionnote=submissionnote,
                                      )
                n.save()
                n.speaker.set(s.speaker.all())
            return HttpResponseRedirect('../')
    else:
        form = CallForPapersCopyForm(conference, speaker)

    return render_conference_response(request, conference, 'cfp', 'confreg/callforpaperscopyform.html', {
        'form': form,
    })


@login_required
def callforpapers_delslides(request, confname, sessionid, slideid):
    conference = get_conference_or_404(confname)
    speaker = get_object_or_404(Speaker, user=request.user)
    session = get_object_or_404(ConferenceSession, conference=conference,
                                speaker=speaker, pk=sessionid)
    slide = get_object_or_404(ConferenceSessionSlides, session=session, id=slideid)
    slide.delete()
    return HttpResponseRedirect('../../')


@login_required
@transaction.atomic
def callforpapers_confirm(request, confname, sessionid):
    conference = get_conference_or_404(confname)

    # Find users speaker record (should always exist when we get this far)
    speaker = get_object_or_404(Speaker, user=request.user)

    # Find the session record (should always exist when we get this far)
    session = get_object_or_404(ConferenceSession, conference=conference,
                                speaker=speaker, pk=sessionid)

    # If there is a pending notification that has not been sent, don't allow
    # confirmation (as it might bypass things). This is normally a can't-happen,
    # since there is no link to confirm at this time, but in concurrent cases...
    if session.status != session.lastnotifiedstatus:
        return HttpResponseRedirect("../..")

    if session.status not in (1, 3, 4, 5):
        # 1 = confirmed, so render
        # 3 = pending, so render form
        # 4 = reserve, so render
        # 5 = pending reserve, so render form
        return HttpResponseRedirect("../..")

    if session.status in (1, 4):
        if not conference.active:
            can_register = False
        elif session.status == 1:
            # If a "speaker" or a "speaker or reserve speaker" regtype exists
            can_register = RegistrationType.objects.filter(conference=conference, active=True, specialtype__in=('spk', 'spkr')).exists()
        else:
            # If a "speaker or reserve speaker" regtype exists
            can_register = RegistrationType.objects.filter(conference=conference, active=True, specialtype='spkr').exists()

        return render_conference_response(request, conference, 'cfp', 'confreg/callforpapersconfirmed.html', {
            'session': session,
            'speaker_can_register': can_register,
        })

    if request.method == 'POST':
        if request.POST.get('is_confirmed', 0) == '1':
            if session.status == 3:
                session.status = 1
            elif session.status == 5:
                session.status = 4
            else:
                # Should not happen case, so just redirect the user back
                return HttpResponseRedirect("../..")
            session.save()
            # We can generate the email for this right away, so let's do that
            for spk in session.speaker.all():
                send_conference_mail(conference,
                                     spk.user.email,
                                     "Your session '{0}'".format(session.title),
                                     'confreg/mail/session_notify_{}.txt'.format(get_status_string_short(session.status)),
                                     {
                                         'conference': conference,
                                         'session': session,
                                     },
                                     receivername=spk.fullname,
                )
            session.lastnotifiedstatus = session.status
            session.lastnotifiedtime = timezone.now()
            session.save()

            if conference.notifysessionstatus:
                # Send notification to the administrators as well
                send_conference_notification_template(
                    conference,
                    "Session confirmation",
                    'confreg/mail/admin_notify_session.txt',
                    {
                        'conference': conference,
                        'session': session,
                    },
                )

            return HttpResponseRedirect(".")

    return render_conference_response(request, conference, 'cfp', 'confreg/callforpapersconfirm.html', {
        'session': session,
    })


@login_required
@transaction.atomic
def confirmreg(request, confname):
    # Confirm a registration step. This will show the user the final
    # cost of the registration, minus any discounts found (including
    # complete-registration vouchers).
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)
    # This should never happen since we should error out in the form,
    # but make sure we don't accidentally proceed.
    if not reg.regtype:
        return render_conference_response(request, conference, 'reg', 'confreg/noregtype.html')
    if reg.bulkpayment:
        return render_conference_response(request, conference, 'reg', 'confreg/bulkpayexists.html')

    # If the registration is *already* confirmed (e.g. somebody went directly to the confirmed page),
    # redirect instead of canceling off waitlist.
    # Same if ethe registration is canceled -- send them back to the dashboard
    if reg.payconfirmedat:
        return HttpResponseRedirect("../")

    registration_warnings = []

    # If there is already an invoice, then this registration has
    # been processed already.
    if reg.invoice:
        return HttpResponseRedirect("/events/%s/register/" % conference.urlname)

    # See if the registration type blocks it
    s = confirm_special_reg_type(reg.regtype.specialtype, reg)
    if s:
        return render_conference_response(request, conference, 'reg', 'confreg/specialregtypeconfirm.html', {
            'reason': s,
            })

    # Is this registration already on the waitlist?
    if hasattr(reg, 'registrationwaitlistentry'):
        if reg.registrationwaitlistentry.offeredon:
            # Waitlist has been offered, but has it expired?
            if reg.registrationwaitlistentry.offerexpires < timezone.now():
                # It has expired
                RegistrationWaitlistHistory(waitlist=reg.registrationwaitlistentry,
                                            text="Offer expired at {0}".format(reg.registrationwaitlistentry.offerexpires)).save()

                reg.registrationwaitlistentry.offeredon = None
                reg.registrationwaitlistentry.offerexpires = None
                # Move registration to the back of the waitlist
                reg.registrationwaitlistentry.enteredon = timezone.now()
                reg.registrationwaitlistentry.save()

                messages.warning(request, "We're sorry, but your registration was not completed in time before the offer expired, and has been moved back to the waitlist.")

                send_conference_notification(
                    conference,
                    'Waitlist expired',
                    'User {0} {1} <{2}> did not complete the registration before the waitlist offer expired.'.format(reg.firstname, reg.lastname, reg.email),
                )

                return render_conference_response(request, conference, 'reg', 'confreg/waitlist_status.html', {
                    'reg': reg,
                })
            else:
                # Offer has not expired, so fall through to below and actually
                # render the form.
                pass
        else:
            # Waitlist has not been offered, but the user is on it
            return render_conference_response(request, conference, 'reg', 'confreg/waitlist_status.html', {
                'reg': reg,
                })
    else:
        # Registration is not on the waitlist, but should it be? Count
        # Check if we do it at all...
        if conference.waitlist_active():
            return render_conference_response(request, conference, 'reg',
                                              'confreg/offer_waitlist.html', {
                                                  'reg': reg,
                                              })

    phone_error = errors = False

    if request.method == 'POST':
        if request.POST['submit'].find('Back') >= 0:
            return HttpResponseRedirect("../")
        if reg.regtype.require_phone:
            reg.phone = request.POST.get('phone', '')
            if len(reg.phone) < 3:
                phone_error = True
                errors = True

        if request.POST['submit'] == 'Confirm and finish' and not errors:
            # Get the invoice rows and flag any vouchers as used
            # (committed at the end of the view so if something
            # goes wrong they automatically go back to unused)
            try:
                invoicerows = invoicerows_for_registration(reg, True)
            except InvoicerowsException:
                # This Should Never Happen (TM) due to validations,
                # so just redirect back to the page for retry.
                return HttpResponseRedirect("../")

            totalcost = sum([r[2] * (1 + (r[3] and r[3].vatpercent or 0) / Decimal(100.0)) for r in invoicerows])

            if len(invoicerows) <= 0:
                return HttpResponseRedirect("../")

            if totalcost == 0:
                # Paid in total with vouchers, or completely free
                # registration type. So just flag the registration
                # as confirmed.
                reg.payconfirmedat = timezone.now()
                reg.payconfirmedby = "no payment reqd"
                reg.save()
                reglog(reg, "Copmleted registraiton not requiring payment", request.user)
                notify_reg_confirmed(reg)
                return HttpResponseRedirect("../")

            # Else there is a cost, so we create an invoice for that
            # cost. Registration will be confirmed when the invoice is paid.
            manager = InvoiceManager()
            processor = InvoiceProcessor.objects.get(processorname="confreg processor")

            # Figure out when to autocancel this invoice, if at all.
            autocancel = get_invoice_autocancel(conference.invoice_autocancel_hours,
                                                reg.regtype.invoice_autocancel_hours,
                                                *[a.invoice_autocancel_hours for a in reg.additionaloptions.filter(invoice_autocancel_hours__isnull=False)])
            if hasattr(reg, 'registrationwaitlistentry'):
                # We're on the waitlist. We've already checked that this is
                # OK, but this value might control how long the invoice is
                # available.
                if autocancel is None or reg.registrationwaitlistentry.offerexpires < autocancel:
                    autocancel = reg.registrationwaitlistentry.offerexpires

            reg.invoice = manager.create_invoice(
                request.user,
                request.user.email,
                reg.firstname + ' ' + reg.lastname,
                reg.company + "\n" + reg.address + "\n" + reg.countryname,
                "%s registration for %s" % (conference.conferencename, reg.email),
                timezone.now(),
                timezone.now(),
                invoicerows,
                processor=processor,
                processorid=reg.pk,
                accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
                accounting_object=conference.accounting_object,
                canceltime=autocancel,
                paymentmethods=conference.paymentmethods.all(),
            )

            reg.invoice.save()
            reg.save()
            reglog(reg, "Confirmed reg details, invoice created", request.user)
            return HttpResponseRedirect("../invoice/%s/" % reg.pk)

        # Else this is some random button we haven't heard of, so just
        # fall through and show the form again.

    # Figure out what should go on the invoice. Don't flag possible
    # vouchers as used, since confirmation isn't done yet.
    try:
        invoicerows = invoicerows_for_registration(reg, False)
    except InvoicerowsException:
        # This should not be possible because of previous validations,
        # so if it does just redirect back for retry.
        return HttpResponseRedirect("../")

    for r in invoicerows:
        # Calculate the with-vat information for this row
        if r[3]:
            r.append(r[2] * (100 + r[3].vatpercent) / Decimal(100))
        else:
            r.append(r[2])

    totalcost = sum([r[2] for r in invoicerows])
    totalwithvat = sum([r[4] for r in invoicerows])

    # It should be impossible to end up with zero invoice rows, so just
    # redirect back if that happens
    if len(invoicerows) <= 0:
        return HttpResponseRedirect("../")

    # Add warnings for mismatching name
    if reg.firstname != request.user.first_name or reg.lastname != request.user.last_name:
        registration_warnings.append("Registration name ({0} {1}) does not match account name ({2} {3}). Please make sure that this is correct, and that you are <strong>not</strong> registering using a different account than your own, as access to the account may be needed during the event!".format(reg.firstname, reg.lastname, request.user.first_name, request.user.last_name))

    return render_conference_response(request, conference, 'reg', 'confreg/regform_confirm.html', {
        'reg': reg,
        'invoicerows': invoicerows,
        'totalcost': totalcost,
        'totalwithvat': totalwithvat,
        'regalert': reg.regtype.alertmessage,
        'warnings': registration_warnings,
        'phone': reg.phone,
        'phone_error': phone_error,
        })


@login_required
@transaction.atomic
def waitlist_signup(request, confname):
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

    # CSRF ensures that this post comes from us.
    if request.POST['submit'] != 'Sign up on waitlist':
        raise Exception("Invalid post button")
    if request.POST.get('confirm', 0) != '1':
        messages.warning(request, "You must check the box to confirm signing up on the waitlist")
        return HttpResponseRedirect("../confirm/")

    if hasattr(reg, 'registrationwaitlistentry'):
        raise Exception("This registration is already on the waitlist")

    # Ok, so put this registration on the waitlist
    waitlist = RegistrationWaitlistEntry(registration=reg)
    waitlist.save()

    RegistrationWaitlistHistory(waitlist=waitlist, text="Signed up for waitlist").save()

    # Notify the conference organizers
    send_conference_notification(
        conference,
        'Waitlist signup',
        'User {0} {1} <{2}> signed up for the waitlist.'.format(reg.firstname, reg.lastname, reg.email),
    )

    # Once on the waitlist, redirect back to the registration form page
    # which will show the waitlist information.
    return HttpResponseRedirect("../confirm/")


@login_required
@transaction.atomic
def waitlist_cancel(request, confname):
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

    # CSRF ensures that this post comes from us.
    if request.POST['submit'] != 'Cancel waitlist':
        raise Exception("Invalid post button")
    if request.POST.get('confirm', 0) != '1':
        messages.warning(request, "You must check the box to confirm canceling your position on the waitlist.")
        return HttpResponseRedirect("../confirm/")

    if not hasattr(reg, 'registrationwaitlistentry'):
        raise Exception("This registration is not on the waitlist")

    reg.registrationwaitlistentry.delete()

    # Notify the conference organizers
    send_conference_notification(
        conference,
        'Waitlist cancel',
        'User {0} {1} <{2}> canceled from the waitlist.'.format(reg.firstname, reg.lastname, reg.email),
    )

    messages.info(request, "Your registration has been removed from the waitlist. You may re-enter it if you change your mind.")

    # Once on the waitlist, redirect back to the registration form page
    # which will show the waitlist information.
    return HttpResponseRedirect("../confirm/")


@login_required
def cancelreg(request, confname):
    conference = get_conference_or_404(confname)
    return render_conference_response(request, conference, 'reg', 'confreg/canceled.html')


@login_required
@transaction.atomic
def invoice(request, confname, regid):
    # Show the invoice. We do this in a separate view from the main view,
    # even though the invoice is present on the main view as well, in order
    # to make things even more obvious.
    # Assumes that the actual invoice has already been created!
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, id=regid, attendee=request.user, conference=conference)

    if reg.bulkpayment:
        return render_conference_response(request, conference, 'reg', 'confreg/bulkpayexists.html')

    if not reg.invoice:
        # We should never get here if we don't have an invoice. If it does
        # happen, just redirect back.
        return HttpResponseRedirect('../../')

    if reg.invoice.canceltime and reg.invoice.canceltime < timezone.now() and not reg.payconfirmedat:
        # Yup, should be canceled
        manager = InvoiceManager()
        manager.cancel_invoice(reg.invoice,
                               "Invoice was automatically canceled because payment was not received on time.",
                               "system")
        return HttpResponseRedirect('../../')

    return render_conference_response(request, conference, 'reg', 'confreg/invoice.html', {
        'reg': reg,
        'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/%s/register/" % (settings.SITEBASE, conference.urlname)),
    })


@login_required
@transaction.atomic
def invoice_cancel(request, confname, regid):
    # Show an optional cancel of this invoice
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, id=regid, attendee=request.user, conference=conference)

    if not reg.invoice:
        # We should never get here if we don't have an invoice. If it does
        # happen, just redirect back.
        return HttpResponseRedirect('../../../')
    if reg.payconfirmedat:
        # If the invoice is already paid while we were waiting, don't allow
        # cancellation any more.
        return HttpResponseRedirect('../../../')

    if request.method == 'POST':
        if request.POST['submit'].find('Cancel invoice') >= 0:
            manager = InvoiceManager()
            manager.cancel_invoice(reg.invoice, "User {0} requested cancellation".format(request.user), request.user.username)
            return HttpResponseRedirect('../../../')
        else:
            return HttpResponseRedirect('../')

    return render_conference_response(request, conference, 'reg', 'confreg/invoicecancel.html', {
        'reg': reg,
    })


@login_required
def attendee_mail(request, confname, mailid):
    conference = get_conference_or_404(confname)
    reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

    mail = _attendeemail_queryset(conference, reg).filter(pk=mailid)
    if len(mail) != 1:
        raise Http404()
    mail = mail[0]

    return render_conference_response(request, conference, 'reg', 'confreg/attendee_mail_view.html', {
        'conference': conference,
        'mail': mail,
        })


@login_required
def download_ticket(request, confname):
    conference = get_conference_or_404(confname)
    if not conference.tickets:
        raise Http404()

    reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

    resp = HttpResponse(content_type='application/pdf')
    render_jinja_ticket(reg, resp, systemroot=JINJA_TEMPLATE_ROOT)
    return resp


@login_required
def view_ticket(request, confname):
    conference = get_conference_or_404(confname)
    if not conference.tickets:
        raise Http404()

    reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

    return render_conference_response(request, conference, 'reg', 'confreg/view_ticket.html', {
        'conference': conference,
        'reg': reg,
        'qrcode': generate_base64_qr(reg.fullidtoken, None, 300),
        })


@transaction.atomic
def optout(request, token=None):
    if token:
        try:
            reg = ConferenceRegistration.objects.get(regtoken=token)
            userid = reg.attendee_id
            email = reg.email
        except ConferenceRegistration.DoesNotExist:
            try:
                speaker = Speaker.objects.get(speakertoken=token)
                userid = speaker.user_id
                email = speaker.user.email
            except Speaker.DoesNotExist:
                raise Http404("Token not found")
    else:
        # No token, so require login
        if not request.user.is_authenticated:
            return HttpResponseRedirect('%s?next=%s' % (settings.LOGIN_URL, request.path))
        userid = request.user.id
        email = request.user.email

    if request.method == 'POST':
        global_optout = request.POST.get('global', '0') == '1'
        sids = exec_to_list("SELECT id FROM confreg_conferenceseries")
        optout_ids = [i for i, in sids if request.POST.get('series_{0}'.format(i), '0') == '1']

        if global_optout:
            exec_no_result('INSERT INTO confreg_globaloptout (user_id) VALUES (%(u)s) ON CONFLICT DO NOTHING', {'u': userid})
        else:
            exec_no_result('DELETE FROM confreg_globaloptout WHERE user_id=%(u)s', {'u': userid})

        exec_no_result('DELETE FROM confreg_conferenceseriesoptout WHERE user_id=%(u)s AND NOT series_id=ANY(%(series)s)', {
            'u': userid,
            'series': optout_ids,
        })
        exec_no_result('INSERT INTO confreg_conferenceseriesoptout (series_id, user_id) SELECT s, %(u)s FROM UNNEST(%(series)s::int[]) s(s) WHERE NOT EXISTS (SELECT 1 FROM confreg_conferenceseriesoptout o WHERE o.user_id=%(u)s AND o.series_id=s.s) ON CONFLICT DO NOTHING', {
            'u': userid,
            'series': optout_ids,
        })
        return HttpResponse("Your conference opt-out settings have been updated.")

    series = exec_to_dict("SELECT s.id, s.name, oo IS NOT NULL AS optout FROM confreg_conferenceseries s LEFT JOIN confreg_conferenceseriesoptout oo ON oo.series_id=s.id AND oo.user_id=%(userid)s", {
        'userid': userid,
    })

    return render(request, 'confreg/optout.html', {
        'email': email,
        'globaloptout': GlobalOptOut.objects.filter(user=userid).exists(),
        'series': series,
    })


@transaction.atomic
def createvouchers(request, confname):
    conference = get_authenticated_conference(request, confname)

    # Creation of pre-paid vouchers for conference registrations
    if request.method == 'POST':
        form = PrepaidCreateForm(conference, data=request.POST)
        if form.is_valid():
            # All data is correct, create the vouchers
            # (by first creating a batch)

            regtype = RegistrationType.objects.get(pk=form.data['regtype'], conference=conference)
            regcount = int(form.data['count'])
            buyer = User.objects.get(pk=form.data['buyer'])
            buyername = '{0} {1}'.format(buyer.first_name, buyer.last_name)

            if form.data.get('invoice', False):
                # This should be invoiced, and thus *not* created immediately.

                invoice = create_voucher_invoice(conference,
                                                 form.data['invoiceaddress'],
                                                 buyer,
                                                 regtype,
                                                 regcount)

                pv = PurchasedVoucher(conference=conference,
                                      sponsor=None,
                                      user=buyer,
                                      regtype=regtype,
                                      num=regcount,
                                      invoice=invoice)
                pv.save()
                invoice.processorid = pv.pk
                invoice.save()

                wrapper = InvoiceWrapper(invoice)
                wrapper.email_invoice()

                return HttpResponseRedirect('../prepaidorders/')
            else:
                # No invoice, so create the vouchers immediately
                batch = PrepaidBatch(conference=conference,
                                     regtype=regtype,
                                     buyer=buyer,
                                     buyername=buyername)
                batch.save()

                for n in range(0, regcount):
                    v = PrepaidVoucher(conference=conference,
                                       vouchervalue=base64.b64encode(os.urandom(37)).rstrip(b'=').decode('utf8'),
                                       batch=batch)
                    v.save()
            return HttpResponseRedirect('%s/' % batch.id)
        # Else fall through to re-render
    else:
        # Get request means we render an empty form
        form = PrepaidCreateForm(conference)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'whatverb': 'Create',
        'what': 'prepaid vouchers',
        'savebutton': 'Create',
        'breadcrumbs': (('/events/admin/{0}/prepaid/list/'.format(conference.urlname), 'Prepaid vouchers'),),
    })


def listvouchers(request, confname):
    conference = get_authenticated_conference(request, confname)

    batches = PrepaidBatch.objects.select_related('regtype', 'purchasedvoucher', 'purchasedvoucher__invoice').filter(conference=conference).prefetch_related('prepaidvoucher_set')

    return render(request, 'confreg/prepaid_list.html', {
        'conference': conference,
        'batches': batches,
        'helplink': 'vouchers',
    })


def viewvouchers(request, confname, batchid):
    conference = get_authenticated_conference(request, confname)

    batch = get_object_or_404(PrepaidBatch, conference=conference, pk=batchid)
    vouchers = batch.prepaidvoucher_set.all()

    vouchermailtext = render_jinja_conference_template(conference, 'confreg/mail/prepaid_vouchers.txt', {
        'batch': batch,
        'vouchers': vouchers,
        'conference': conference,
        })

    return render(request, 'confreg/prepaid_create_list.html', {
        'conference': conference,
        'batch': batch,
        'vouchers': vouchers,
        'vouchermailtext': vouchermailtext,
        'breadcrumbs': (('/events/admin/{0}/prepaid/list/'.format(conference.urlname), 'Prepaid vouchers'),),
        'helplink': 'vouchers',
    })


@transaction.atomic
def delvouchers(request, confname, batchid, voucherid):
    conference = get_authenticated_conference(request, confname)

    batch = get_object_or_404(PrepaidBatch, conference=conference, pk=batchid)
    voucher = get_object_or_404(PrepaidVoucher, batch=batch, pk=voucherid)

    if voucher.user or voucher.usedate:
        messages.error(request, "Unable to delete voucher, it has been used!")
    else:
        # OK, delete the voucher
        vcode = voucher.vouchervalue
        voucher.delete()
        messages.info(request, "Voucher {0} deleted.".format(vcode))
        if not batch.prepaidvoucher_set.exists():
            # Nothing left, so delete the batch
            batch.delete()
            messages.info(request, "Batch {0} now empty, so also deleted.".format(batchid))

    return HttpResponseRedirect('/events/admin/{0}/prepaid/list/'.format(confname))


@login_required
def viewvouchers_user(request, confname, batchid):
    conference = get_conference_or_404(confname)
    batch = get_object_or_404(PrepaidBatch, conference=conference, pk=batchid)
    if batch.buyer != request.user:
        raise PermissionDenied()
    vouchers = batch.prepaidvoucher_set.all()

    return render_conference_response(request, conference, 'reg', 'confreg/prepaid_list.html', {
        'batch': batch,
        'vouchers': vouchers,
    })


def emailvouchers(request, confname, batchid):
    conference = get_authenticated_conference(request, confname)

    batch = PrepaidBatch.objects.get(pk=batchid)
    vouchers = batch.prepaidvoucher_set.all()

    send_conference_mail(batch.conference,
                         batch.buyer.email,
                         "Attendee vouchers",
                         'confreg/mail/prepaid_vouchers.txt',
                         {
                             'batch': batch,
                             'vouchers': vouchers,
                             'conference': conference,
                         },
                         receivername="{0} {1}".format(batch.buyer.first_name, batch.buyer.last_name),
    )
    return HttpResponse('OK')


@login_required
@transaction.atomic
def talkvote(request, confname):
    conference = get_conference_or_404(confname)

    isvoter = conference.talkvoters.filter(pk=request.user.id).exists()
    isadmin = conference.administrators.filter(pk=request.user.id).exists() or conference.series.administrators.filter(pk=request.user.id).exists()

    if not isvoter and not isadmin:
        raise PermissionDenied('You are not a talk voter or administrator for this conference!')

    alltracks = [{'id': t.id, 'trackname': t.trackname} for t in Track.objects.filter(conference=conference)]
    alltracks.insert(0, {'id': 0, 'trackname': 'No track'})
    alltrackids = [t['id'] for t in alltracks]
    selectedtracks = [int(id) for id in request.GET.getlist('tracks') if int(id) in alltrackids]
    allstatusids = [id for id, status in STATUS_CHOICES]
    selectedstatuses = [int(id) for id in request.GET.getlist('statuses') if int(id) in allstatusids]
    if selectedtracks:
        urltrackfilter = "{0}&".format("&".join(["tracks={0}".format(t) for t in selectedtracks]))
    else:
        selectedtracks = alltrackids
        urltrackfilter = ''

    if selectedstatuses:
        urlstatusfilter = "{0}&".format("&".join(["statuses={0}".format(t) for t in selectedstatuses]))
    else:
        selectedstatuses = allstatusids
        urlstatusfilter = ''

    curs = connection.cursor()

    order = ""
    if 'sort' in request.GET:
        if request.GET["sort"] == "avg":
            order = "avg DESC NULLS LAST,"
        elif request.GET["sort"] == "speakers":
            order = "speakers_full, avg DESC NULLS LAST,"
        elif request.GET["sort"] == "session":
            order = "s.title, avg DESC NULLS LAST,"

    # Render the form. Need to do this with a manual query, can't figure
    # out the right way to do it with the django ORM.
    curs.execute("SELECT s.id, s.title, s.status, s.lastnotifiedstatus, s.abstract, s.submissionnote, (SELECT string_agg(spk.fullname, ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers, (SELECT string_agg(spk.fullname || '(' || spk.company || ')', ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_full, (SELECT string_agg('####' || spk.fullname || ' [speaker id: ' || spk.id || ']' || '\n' || spk.abstract, '\n\n') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_long, u.username, v.vote, v.comment, avg(v.vote) OVER (PARTITION BY s.id)::numeric(3,2) AS avg, trackname FROM (confreg_conferencesession s CROSS JOIN auth_user u) LEFT JOIN confreg_track track ON track.id=s.track_id LEFT JOIN confreg_conferencesessionvote v ON v.session_id=s.id AND v.voter_id=u.id WHERE s.conference_id=%(confid)s AND u.id IN (SELECT user_id FROM confreg_conference_talkvoters tv WHERE tv.conference_id=%(confid)s) AND (COALESCE(s.track_id,0)=ANY(%(tracks)s)) AND status=ANY(%(statuses)s) ORDER BY " + order + "s.title,s.id, u.id=%(userid)s DESC, u.username", {
        'confid': conference.id,
        'userid': request.user.id,
        'tracks': selectedtracks,
        'statuses': selectedstatuses,
    })

    def getusernames(all):
        if not all:
            return

        firstid = all[0][0]
        for id, title, status, laststatus, abstract, submissionnote, speakers, speakers_full, speakers_long, username, vote, comment, avgvote, track in all:
            if id != firstid:
                return
            yield username

    def transform(all):
        if not all:
            return

        lastid = -1
        rd = {}
        for id, title, status, laststatus, abstract, submissionnote, speakers, speakers_full, speakers_long, username, vote, comment, avgvote, track in all:
            if id != lastid:
                if lastid != -1:
                    yield rd
                rd = {
                    'id': id,
                    'title': title,
                    'statusid': status,
                    'status': get_status_string(status),
                    'laststatusid': laststatus,
                    'abstract': abstract,
                    'submissionnote': submissionnote,
                    'speakers': speakers,
                    'speakers_full': speakers_full,
                    'speakers_long': speakers_long,
                    'avg': avgvote,
                    'users': [],
                    'comments': '',
                    'owncomment': '',
                    'track': track,
                    }
                lastid = id
            rd['users'].append(vote)
            if comment:
                if username == request.user.username:
                    rd['owncomment'] = comment
                else:
                    rd['comments'] += "%s: %s<br/>" % (username, comment)

        yield rd

    all = curs.fetchall()

    # If the user is only talkvoter at the conference, and not an administrator,
    # don't generate a breadcrumbs link that goes to a permission denied error.
    if not isadmin:
        conference.nobreadcrumb = True

    return render(request, 'confreg/sessionvotes.html', {
        'users': getusernames(all),
        'sessionvotes': transform(all),
        'conference': conference,
        'isvoter': isvoter,
        'isadmin': isadmin,
        'status_choices': STATUS_CHOICES,
        'tracks': alltracks,
        'selectedtracks': selectedtracks,
        'selectedstatuses': selectedstatuses,
        'valid_status_transitions': valid_status_transitions,
        'urlfilter': urltrackfilter + urlstatusfilter,
        'helplink': 'callforpapers',
    })


@login_required
@transaction.atomic
def talkvote_status(request, confname):
    conference = get_conference_or_404(confname)
    if not conference.talkvoters.filter(pk=request.user.id).exists() and not conference.administrators.filter(pk=request.user.id).exists() and not conference.series.administrators.filter(pk=request.user.id).exists():
        raise PermissionDenied('You are not a talk voter or administrator for this conference!')

    isadmin = conference.administrators.filter(pk=request.user.id).exists() or conference.series.administrators.filter(pk=request.user.id).exists()
    if not isadmin:
        raise PermissionDenied('Only admins can change the status')

    if request.method != 'POST':
        return HttpResponse('Can only use POST', status_code=400)

    if 'newstatus' not in request.POST:
        raise Http404("No new status")
    if 'sessionid' not in request.POST:
        raise Http404("No sessionid")

    newstatus = get_int_or_error(request.POST, 'newstatus')
    session = get_object_or_404(ConferenceSession, conference=conference, id=get_int_or_error(request.POST, 'sessionid'))
    if newstatus not in valid_status_transitions[session.status]:
        return HttpResponse("Cannot change from {} to {}".format(get_status_string(session.status), get_status_string(newstatus)), status=400)

    session.status = newstatus
    session.save()
    statechange = session.speaker.exists() and (session.status != session.lastnotifiedstatus)

    if statechange:
        # If *this* session has a state changed, then we can shortcut the lookup for
        # others and just indicate we know there is one.
        pendingnotifications = True
    else:
        # Otherwise we have to see if there are any others
        pendingnotifications = conference.pending_session_notifications

    return HttpResponse(json.dumps({
        'newstatus': get_status_string(session.status),
        'statechanged': statechange,
        'pending': bool(pendingnotifications),
    }), content_type='application/json')


@login_required
@transaction.atomic
def talkvote_vote(request, confname):
    conference = get_conference_or_404(confname)
    if not conference.talkvoters.filter(pk=request.user.id):
        raise PermissionDenied('You are not a talk voter for this conference!')
    if request.method != 'POST':
        return HttpResponse('Can only use POST')

    if 'sessionid' not in request.POST:
        raise Http404("No sessionid")

    session = get_object_or_404(ConferenceSession, conference=conference, id=get_int_or_error(request.POST, 'sessionid'))
    v = get_int_or_error(request.POST, 'vote', 0)
    if v > 0:
        vote, created = ConferenceSessionVote.objects.get_or_create(session=session, voter=request.user)
        vote.vote = v
        vote.save()
    else:
        ConferenceSessionVote.objects.filter(session=session, voter=request.user).delete()

    # Re-calculate the average
    avg = session.conferencesessionvote_set.all().aggregate(Avg('vote'))['vote__avg']
    if avg is None:
        avg = 0
    return HttpResponse("{0:.2f}".format(avg), content_type='text/plain')


@login_required
@transaction.atomic
def talkvote_comment(request, confname):
    conference = get_conference_or_404(confname)
    if not conference.talkvoters.filter(pk=request.user.id):
        raise PermissionDenied('You are not a talk voter for this conference!')
    if request.method != 'POST':
        return HttpResponse('Can only use POST')
    if 'sessionid' not in request.POST:
        raise Http404("No sessionid")

    session = get_object_or_404(ConferenceSession, conference=conference, id=get_int_or_error(request.POST, 'sessionid'))
    vote, created = ConferenceSessionVote.objects.get_or_create(session=session, voter=request.user)
    vote.comment = request.POST.get('comment', '')
    vote.save()

    return HttpResponse(vote.comment, content_type='text/plain')


@login_required
@transaction.atomic
def createschedule(request, confname):
    conference = get_conference_or_404(confname)
    is_admin = conference.administrators.filter(pk=request.user.id).exists() or conference.series.administrators.filter(pk=request.user.id).exists()
    if not (request.user.is_superuser or is_admin or
            conference.talkvoters.filter(pk=request.user.id).exists()
            ):
        raise PermissionDenied('You are not an administrator or talk voter for this conference!')

    if request.method == "GET":
        if request.GET.get('get', 0) == '1':
            # Get the current list of tentatively scheduled talks
            # Explicitly exclude those that are not approved/pending (can happen if a session was first approved, then scheduled,
            # and then unapproved)
            s = {}
            for sess in conference.conferencesession_set.filter(status__in=(1, 3), tentativeroom__isnull=False, tentativescheduleslot__isnull=False):
                s['slot%s' % ((sess.tentativeroom.id * 1000000) + sess.tentativescheduleslot.id)] = 'sess%s' % sess.id
            return HttpResponse(json.dumps(s), content_type="application/json")
        # Else it was a get for the page so fall through
    elif request.method == "POST":
        # Else we are saving. This is only allowed by superusers and administrators,
        # not all talk voters (as it potentially changes the website).
        if not request.user.is_superuser and not is_admin:
            raise PermissionDenied('Only administrators can save!')

        # Remove all the existing mappings, and add new ones
        # Yes, we do this horribly inefficiently, but it doesn't run very
        # often at all...
        re_slot = re.compile(r'^slot(\d+)$')
        for sess in conference.conferencesession_set.all():
            found = False
            for k, v in list(request.POST.items()):
                if v == "sess%s" % sess.id:
                    sm = re_slot.match(k)
                    if not sm:
                        raise Exception("Could not find slot, invalid data in POST")
                    roomid = int(int(sm.group(1)) // 1000000)
                    slotid = int(sm.group(1)) % 1000000
                    if sess.tentativeroom is None or sess.tentativeroom.id != roomid or sess.tentativescheduleslot is None or sess.tentativescheduleslot.id != slotid:
                        sess.tentativeroom = Room.objects.get(pk=roomid)
                        sess.tentativescheduleslot = ConferenceSessionScheduleSlot.objects.get(pk=slotid)
                        sess.save()
                    found = True
                    break
            if not found:
                if sess.tentativescheduleslot:
                    sess.tentativescheduleslot = None
                    sess.save()
        return HttpResponse("OK")

    # Not post - so generate the page

    allrooms = exec_to_keyed_dict("SELECT id, sortkey, url, roomname, comment AS roomcomment FROM confreg_room r WHERE conference_id=%(confid)s ORDER BY sortkey, roomname", {
        'confid': conference.id,
    })
    if len(allrooms) == 0:
        return HttpResponse('No rooms defined for this conference, cannot create schedule yet.')

    with ensure_conference_timezone(conference):
        # Complete list of all available sessions
        sessions = exec_to_dict("SELECT s.id, track_id, (status = 3) AS ispending, (row_number() over() +1)*75 AS top, title, string_agg(spk.fullname, ', ') AS speaker_list FROM confreg_conferencesession s LEFT JOIN confreg_conferencesession_speaker csp ON csp.conferencesession_id=s.id LEFT JOIN confreg_speaker spk ON spk.id=csp.speaker_id WHERE conference_id=%(confid)s AND status IN (1,3) AND NOT cross_schedule GROUP BY s.id ORDER BY starttime, id", {
            'confid': conference.id,
        })

        # Generate a sessionset with the slots only, but with one slot for
        # each room when we have multiple rooms.
        raw = exec_to_grouped_dict("""SELECT
    s.starttime::date AS day,
    r.id * 1000000 + s.id AS id,
    s.starttime, s.endtime,
    r.id AS room_id,
    to_char(starttime, 'HH24:MI') || ' - ' || to_char(endtime, 'HH24:MI') AS timeslot,
    min(starttime) OVER days AS firsttime,
    max(endtime) OVER days AS lasttime,
    'f'::boolean as cross_schedule
FROM confreg_conferencesessionscheduleslot s
CROSS JOIN confreg_room r
WHERE
    r.conference_id=%(confid)s AND
    s.conference_id=%(confid)s AND (
      EXISTS (SELECT 1 FROM confreg_room_availabledays ad
              INNER JOIN confreg_registrationday rd ON rd.id=ad.registrationday_id
              WHERE ad.room_id=r.id AND rd.day=s.starttime::date)
      OR NOT EXISTS (SELECT 1 FROM confreg_room_availabledays ad2 WHERE ad2.room_id=r.id)
    )
WINDOW days AS (PARTITION BY s.starttime::date)
ORDER BY day, s.starttime""", {
            'confid': conference.id,
        })

    if len(raw) == 0:
        return HttpResponse('No schedule slots defined for this conference, cannot create schedule yet.')

    tracks = Track.objects.filter(conference=conference).order_by('sortkey')

    days = []

    for d, d_sessions in list(raw.items()):
        # All rooms possibly not available on all days, so re-query
        rooms = exec_to_scalar("""SELECT
   array_agg(id ORDER BY sortkey, roomname)
FROM confreg_room r
WHERE conference_id=%(confid)s
AND (
   EXISTS (SELECT 1 FROM confreg_room_availabledays ad
        INNER JOIN confreg_registrationday rd ON rd.id=ad.registrationday_id
        WHERE ad.room_id=r.id AND rd.conference_id=%(confid)s AND rd.day=%(day)s
   ) OR NOT EXISTS (
        SELECT 1 FROM confreg_room_availabledays ad2 WHERE ad2.room_id=r.id
   )
)""", {
            'confid': conference.id,
            'day': d,
        })

        sessionset = SessionSet(allrooms, rooms, conference.schedulewidth, conference.pixelsperminute, conference.feedbackopen, d_sessions)
        days.append({
            'day': d,
            'sessions': sessionset.all(),
            'rooms': sessionset.allrooms(),
            'schedule_height': sessionset.schedule_height(),
            'schedule_width': sessionset.schedule_width(),
        })
    return render(request, 'confreg/schedule_create.html', {
        'conference': conference,
        'days': days,
        'sessions': sessions,
        'tracks': tracks,
        'sesswidth': min(600 // len(allrooms), 150),
        'availableheight': len(sessions) * 75,
        'helplink': 'schedule',
    })


@login_required
def publishschedule(request, confname):
    conference = get_authenticated_conference(request, confname)

    transaction.set_autocommit(False)

    changes = []
    # Render a list of changes and a confirm button
    for s in conference.conferencesession_set.all():
        dirty = False
        if s.tentativescheduleslot:
            # It has one, see if it has changed
            if s.starttime:
                # Has an existing time, did it change?
                if s.starttime != s.tentativescheduleslot.starttime or s.endtime != s.tentativescheduleslot.endtime:
                    changes.append("Session '%s': moved from '%s' to '%s'" % (s.title, s.starttime, s.tentativescheduleslot.starttime))
                    s.starttime = s.tentativescheduleslot.starttime
                    s.endtime = s.tentativescheduleslot.endtime
                    dirty = True
            else:
                # Previously had no time
                if s.tentativescheduleslot:
                    changes.append("Session '%s': now scheduled at '%s'" % (s.title, s.tentativescheduleslot))
                    s.starttime = s.tentativescheduleslot.starttime
                    s.endtime = s.tentativescheduleslot.endtime
                    dirty = True
            if s.room != s.tentativeroom:
                changes.append("Session '%s': changed room from '%s' to '%s'" % (s.title, s.room, s.tentativeroom))
                s.room = s.tentativeroom
                dirty = True
        else:
            if s.starttime:
                changes.append("Session '%s': NOT removed from schedule, do that manually!" % s.title)

        if dirty:
            s.save()

    if request.method == 'POST' and request.POST.get('doit', 0) == '1':
        transaction.commit()
        return render(request, 'confreg/schedule_publish.html', {
            'done': 1,
        })
    else:
        transaction.rollback()
        return render(request, 'confreg/schedule_publish.html', {
            'changes': changes,
        })


def reports(request, confname):
    conference = get_authenticated_conference(request, confname)

    # Include information for the advanced reports
    from .reports import attendee_report_fields, attendee_report_filters, build_attendee_report

    if request.method == 'POST':
        if request.POST['what'] == 'delete':
            if request.POST.get('storedreport', '') == '':
                raise Http404()

            get_object_or_404(SavedReportDefinition, conference=conference, pk=get_int_or_error(request.POST, 'storedreport')).delete()
            return HttpResponse("OK")

        data = json.loads(request.POST['reportdata'])
        if request.POST['what'] == 'generate':
            return build_attendee_report(request, conference, data)
        elif request.POST['what'] == 'save':
            with transaction.atomic():
                if request.POST.get('overwrite', 0) == "1":
                    obj = get_object_or_404(SavedReportDefinition, conference=conference, title=request.POST['name'])
                    obj.definition = data
                    obj.save()
                else:
                    if SavedReportDefinition.objects.filter(conference=conference, title=request.POST['name']).exists():
                        return HttpResponse("Already exists", status=409)

                    SavedReportDefinition(conference=conference,
                                          title=request.POST['name'],
                                          definition=data).save()
                return HttpResponse("OK")
        raise Http404()
    elif 'storedreport' in request.GET:
        # Load a special stored report
        if request.GET.get('storedreport', '') == '':
            raise Http404()

        r = get_object_or_404(SavedReportDefinition, conference=conference, pk=get_int_or_error(request.GET, 'storedreport'))
        return HttpResponse(json.dumps(r.definition), content_type='application/json')

    return render(request, 'confreg/reports.html', {
        'conference': conference,
        'additionaloptions': conference.conferenceadditionaloption_set.all(),
        'adv_fields': attendee_report_fields,
        'adv_filters': attendee_report_filters(conference),
        'stored_reports': SavedReportDefinition.objects.filter(conference=conference).order_by('title'),
        'helplink': 'reports#attendee',
    })


def simple_report(request, confname):
    conference = get_authenticated_conference(request, confname)

    from .reports import simple_reports

    if request.method == 'GET':
        if 'report' not in request.GET:
            raise Http404("No report")
        rep = request.GET['report']
    else:
        if 'report' not in request.POST:
            raise Http404("No report")
        rep = request.POST['report']

    if "__" in rep:
        raise Http404("Invalid character in report name")

    if rep not in simple_reports:
        raise Http404("Report not found")

    if conference.personal_data_purged and '{0}__anon'.format(rep) in simple_reports:
        query = simple_reports['{0}__anon'.format(rep)]
    else:
        query = simple_reports[rep]

    params = {
        'confid': conference.id,
    }

    if not isinstance(query, str):
        if request.method == 'POST':
            form = query(data=request.POST, initial={'report': rep})
            if form.is_valid():
                query = form.build_query(conference)
                params.update(form.extra_params())
                form = None
        else:
            form = query(initial={'report': rep})
        if form:
            return render(request, 'confreg/admin_backend_form.html', {
                'conference': conference,
                'basetemplate': 'confreg/confadmin_base.html',
                'form': form,
                'savebutton': 'Generate report',
            })

    with ensure_conference_timezone(conference) as curs:
        curs.execute(query, params)

    d = curs.fetchall()
    collist = [dd[0] for dd in curs.description]
    # Get offsets of all columns that don't start with _
    colofs = [n for x, n in zip(collist, list(range(len(collist)))) if not x.startswith('_')]
    if len(colofs) != len(collist):
        # One or more columns filtered - so filter the data
        d = list(map(itemgetter(*colofs), d))

    return render(request, 'confreg/simple_report.html', {
        'conference': conference,
        'columns': [dd for dd in collist if not dd.startswith('_')],
        'data': d,
        'helplink': 'reports',
        'backurl': '/events/admin/{0}/'.format(conference.urlname),
        'backwhat': 'dashboard',
    })


@login_required
def admin_dashboard(request):
    if request.user.is_superuser:
        conferences = Conference.objects.filter(startdate__gt=timezone.now() - timedelta(days=14)).order_by('-startdate')
        pastconf_perm = 'true'
        pastconf_where = ''
        pastconf_param = {}
    else:
        conferences = Conference.objects.filter(Q(administrators=request.user) | Q(series__administrators=request.user), startdate__gt=timezone.now() - timedelta(days=14)).distinct().order_by('-startdate')
        pastconf_perm = 'EXISTS (SELECT 1 FROM confreg_conferenceseries_administrators a WHERE a.conferenceseries_id=s.id AND a.user_id=%(user)s)'
        pastconf_where = ' WHERE EXISTS (SELECT 1 FROM confreg_conferenceseries_administrators a WHERE a.conferenceseries_id=s.id AND a.user_id=%(user)s) OR EXISTS (SELECT 1 FROM confreg_conference_administrators ca WHERE ca.conference_id=c.id AND ca.user_id=%(user)s) '
        pastconf_param = {
            'user': request.user.id,
        }

    # If a specific series is specified, then include *all* past conferences for that series
    if request.GET.get('series', None):
        if request.user.is_superuser:
            singleseries = get_object_or_404(ConferenceSeries, pk=get_int_or_error(request.GET, 'series'))
        else:
            singleseries = get_object_or_404(ConferenceSeries, pk=get_int_or_error(request.GET, 'series'), administrators=request.user)
        pastconferences = exec_to_dict("SELECT s.id AS seriesid, s.name AS seriesname, c.conferencename, c.urlname, c.startdate FROM confreg_conference c INNER JOIN confreg_conferenceseries s ON s.id=c.series_id WHERE s.id=%(id)s ORDER BY startdate DESC", {
            'id': singleseries.id,
        })
    else:
        singleseries = None
        pastconferences = exec_to_dict("SELECT s.id AS seriesid, s.name AS seriesname, {} AS seriesperm, c.conferencename, c.urlname, c.startdate, max(startdate) OVER (PARTITION BY s.id) AS maxdate FROM confreg_conferenceseries s INNER JOIN LATERAL (SELECT id, conferencename, urlname, startdate FROM confreg_conference WHERE series_id=s.id ORDER BY startdate DESC LIMIT 4) c ON true {} ORDER BY maxdate DESC, s.name, startdate DESC".format(pastconf_perm, pastconf_where), pastconf_param)

    # Split conferences in two buckets:
    #  Current: anything that starts or finishes within two weeks
    #  Upcoming: anything newer than that

    current = []
    upcoming = []
    for c in conferences:
        if abs((today_conference() - c.startdate).days) < 14 or abs((today_conference() - c.enddate).days) < 14:
            current.insert(0, c)
        elif c.startdate > today_conference():
            upcoming.insert(0, c)

    return render(request, 'confreg/admin_dashboard.html', {
        'current': current,
        'upcoming': upcoming,
        'past': pastconferences,
        'singleseries': singleseries,
        'cross_conference': request.user.is_superuser or ConferenceSeries.objects.filter(administrators=request.user).exists(),
    })


def admin_dashboard_single(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    with ensure_conference_timezone(conference):
        return render(request, 'confreg/admin_dashboard_single.html', {
            'conference': conference,
            'pending_session_notifications': conference.pending_session_notifications,
            'pending_waitlist': RegistrationWaitlistEntry.objects.filter(registration__conference=conference, offeredon__isnull=True).exists(),
            'unregistered_staff': exec_to_scalar("SELECT EXISTS (SELECT user_id FROM confreg_conference_staff s WHERE s.conference_id=%(confid)s AND NOT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND canceledat IS NULL AND attendee_id=s.user_id))", {'confid': conference.id}),
            'unregistered_speakers': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id WHERE s.conference_id=%(confid)s AND s.status=1 AND NOT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL AND r.attendee_id=spk.user_id))", {'confid': conference.id}),
            'unconfirmed_speakers': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession_speaker css INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id WHERE s.conference_id=%(confid)s AND s.status=3)", {'confid': conference.id}),
            'sessions_noroom': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.status=1 AND s.room_id IS NULL AND NOT cross_schedule)", {'confid': conference.id}),
            'sessions_notrack': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.status=1 AND s.track_id IS NULL)", {'confid': conference.id}),
            'sessions_roomoverlap': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s INNER JOIN confreg_room r ON r.id=s.room_id WHERE s.conference_id=%(confid)s AND r.conference_id=%(confid)s AND status=1 AND EXISTS (SELECT 1 FROM confreg_conferencesession s2 WHERE s2.conference_id=%(confid)s AND s2.status=1 AND s2.room_id=s.room_id AND s.id != s2.id AND tstzrange(s.starttime, s.endtime) && tstzrange(s2.starttime, s2.endtime)))", {'confid': conference.id}),
            'pending_sessions': conditional_exec_to_scalar(conference.scheduleactive, "SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.status=0)", {'confid': conference.id}),
            'uncheckedin_attendees': conditional_exec_to_scalar(conference.checkinactive, "SELECT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND canceledat IS NULL AND checkedinat IS NULL)", {'confid': conference.id}),
            'uncheckedin_speakers': conditional_exec_to_scalar(conference.checkinactive, "SELECT EXISTS (SELECT 1 FROM confreg_conferenceregistration r INNER JOIN confreg_speaker spk ON spk.user_id=r.attendee_id INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id INNER JOIN confreg_conferencesession s ON s.id=css.conferencesession_id WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL AND r.checkedinat IS NULL AND s.conference_id=%(confid)s AND s.status=1)", {'confid': conference.id}),
            'pending_sponsors': conditional_exec_to_scalar(conference.callforsponsorsopen, "SELECT EXISTS (SELECT 1 FROM confsponsor_sponsor WHERE conference_id=%(confid)s AND invoice_id IS NULL AND NOT confirmed)", {'confid': conference.id}),
            'pending_sponsor_benefits': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confsponsor_sponsorclaimedbenefit b INNER JOIN confsponsor_sponsor s ON s.id=b.sponsor_id WHERE s.conference_id=%(confid)s AND NOT (b.confirmed OR b.declined))", {'confid': conference.id}),
            'pending_tweets': ConferenceTweetQueue.objects.filter(conference=conference, sent=False).exists(),
            'pending_tweet_approvals': ConferenceTweetQueue.objects.filter(conference=conference, approved=False).exists(),
        })


def admin_registration_dashboard(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    curs = connection.cursor()

    tables = []

    # Registrations by reg type
    curs.execute("""SELECT regtype,
 count(payconfirmedat) - count(canceledat) AS confirmed,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NOT NULL OR bp.invoice_id IS NOT NULL)) AS invoiced,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NULL AND bp.invoice_id IS NULL)) AS unconfirmed,
 count(r.id) - count(canceledat) AS total,
 count(canceledat) AS canceled,
 invoice_autocancel_hours
FROM confreg_conferenceregistration r
RIGHT JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
WHERE rt.conference_id={0}
GROUP BY rt.id ORDER BY rt.sortkey""".format(conference.id))
    tables.append({'title': 'Registration types',
                   'columns': ['Type', 'Confirmed', 'Invoiced', 'Unconfirmed', 'Total', 'Canceled', 'Inv. autoc'],
                   'fixedcols': 1,
                   'fixedcolsend': 1,
                   'hidecols': 0,
                   'rows': curs.fetchall()},)

    # Additional options. We need to run basically two queries (we do so in CTEs) here since
    # an AO can be added both as part of a pending registration and as a pending additional
    # order on a confirmed registration.
    # Pending orders don't count when they are confirmed, since they are then part of the
    # regular ones, but they have to count when they are pending.
    curs.execute("""WITH direct AS (
 SELECT rao.conferenceadditionaloption_id AS aoid,
        count(*) FILTER (WHERE r.payconfirmedat IS NOT NULL) AS confirmed,
        count(*) FILTER (WHERE r.payconfirmedat IS NULL AND (r.invoice_id IS NOT NULL OR bp.invoice_id IS NOT NULL)) AS invoiced,
        count(*) FILTER (WHERE r.payconfirmedat IS NULL AND r.invoice_id IS NULL AND bp.invoice_id IS NULL) AS unconfirmed,
        count(*) AS total
 FROM confreg_conferenceregistration r
 INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id
 LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
 WHERE r.conference_id={0}
 GROUP BY aoid
),
pending AS (
 SELECT paoo.conferenceadditionaloption_id AS aoid,
        count(*) FILTER (WHERE pao.invoice_id IS NOT NULL) AS invoiced,
        count(*) FILTER (WHERE pao.invoice_id IS NULL) AS unconfirmed,
        count(*) AS total
 FROM confreg_pendingadditionalorder_options paoo
 INNER JOIN confreg_pendingadditionalorder pao ON pao.id=paoo.pendingadditionalorder_id
 INNER JOIN confreg_conferenceregistration r ON r.id=pao.reg_id
 WHERE r.conference_id={0} AND pao.payconfirmedat IS NULL
 GROUP BY aoid
)
SELECT ao.id, ao.name, ao.maxcount,
       COALESCE(direct.confirmed, 0) AS confirmed,
       COALESCE(direct.invoiced, 0)+COALESCE(pending.invoiced, 0) AS invoiced,
       COALESCE(direct.unconfirmed, 0)+COALESCE(pending.unconfirmed, 0) AS unconfirmed,
       COALESCE(direct.total, 0)+COALESCE(pending.total, 0) AS total,
       ao.maxcount-COALESCE(direct.total, 0)-COALESCE(pending.total, 0) AS remaining,
       ao.invoice_autocancel_hours
FROM confreg_conferenceadditionaloption ao
LEFT JOIN pending ON pending.aoid=ao.id
LEFT JOIN direct ON direct.aoid=ao.id
WHERE ao.conference_id={0}
""".format(conference.id))

    tables.append({'title': 'Additional options',
                   'columns': ['id', 'Name', 'Max uses', 'Confirmed', 'Invoiced', 'Unconfirmed', 'Total', 'Remaining', 'Inv. autoc'],
                   'fixedcols': 2,
                   'fixedcolsend': 1,
                   'hidecols': 1,
                   'linker': lambda x: '../addopts/{0}/'.format(x[0]),
                   'rows': curs.fetchall()})

    # Discount codes
    curs.execute("""SELECT dc.id, code, validuntil, maxuses,
 count(payconfirmedat) AS confirmed,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NOT NULL OR bp.invoice_id IS NOT NULL)) AS invoiced,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NULL AND bp.invoice_id IS NULL)) AS unconfirmed,
 count(r.id) AS total,
 CASE WHEN maxuses > 0 THEN maxuses-count(r.id) ELSE NULL END AS remaining
FROM confreg_conferenceregistration r
RIGHT JOIN confreg_discountcode dc ON dc.code=r.vouchercode
LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
WHERE dc.conference_id={0} AND (r.conference_id={0} OR r.conference_id IS NULL) GROUP BY dc.id ORDER BY code""".format(conference.id))
    tables.append({'title': 'Discount codes',
                   'columns': ['id', 'Code', 'Expires', 'Max uses', 'Confirmed', 'Invoiced', 'Unconfirmed', 'Total', 'Remaining', ],
                   'fixedcols': 3,
                   'fixedcolsend': 0,
                   'hidecols': 1,
                   'linker': lambda x: '../discountcodes/{0}/'.format(x[0]),
                   'rows': curs.fetchall()})

    # Voucher batches
    curs.execute("SELECT b.id, b.buyername, s.name as sponsorname, count(v.user_id) AS used, count(*) FILTER (WHERE v.user_id IS NULL) AS unused, count(*) AS total FROM confreg_prepaidbatch b INNER JOIN confreg_prepaidvoucher v ON v.batch_id=b.id LEFT JOIN confreg_conferenceregistration r ON r.id=v.user_id LEFT JOIN confsponsor_sponsor s ON s.id = b.sponsor_id WHERE b.conference_id={0} GROUP BY b.id, s.name ORDER BY buyername".format(conference.id))
    tables.append({'title': 'Prepaid vouchers',
                   'columns': ['id', 'Buyer', 'Sponsor', 'Used', 'Unused', 'Total'],
                   'fixedcols': 3,
                   'fixedcolsend': 0,
                   'hidecols': 1,
                   'linker': lambda x: '../prepaid/{0}/'.format(x[0]),
                   'rows': curs.fetchall()})

    # Add a sum row for eveything
    for t in tables:
        sums = ['Total']
        for cn in range(1, t['fixedcols']):
            sums.append('')
        for cn in range(t['fixedcols'] - 1, len(t['columns']) - 1 - t['fixedcolsend']):
            sums.append(sum((r[cn + 1] for r in t['rows'] if r[cn + 1] is not None)))
        for cn in range(0, t['fixedcolsend']):
            sums.append('')
        t['rows'] = [(r, t.get('linker', lambda x: None)(r)) for r in t['rows']]
        t['rows'].append((sums, None))
    return render(request, 'confreg/admin_registration_dashboard.html', {
        'conference': conference,
        'tables': tables,
        'helplink': 'registrations',
    })


def admin_registration_list(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return render(request, 'confreg/admin_registration_list.html', {
        'conference': conference,
        'waitlist_active': conference.waitlist_active(),
        'regs': ConferenceRegistration.objects.select_related('regtype', 'registrationwaitlistentry', 'invoice', 'bulkpayment').extra(select={
            'waitlist_offers_made': """CASE WHEN "confreg_registrationwaitlistentry"."registration_id" IS NULL THEN 0 ELSE (SELECT count(*) FROM confreg_registrationwaitlisthistory h WHERE h.waitlist_id="confreg_registrationwaitlistentry"."registration_id" AND h.text LIKE 'Made offer%%')  END""",
        }).filter(conference=conference),
        'regsummary': exec_to_dict("SELECT count(1) FILTER (WHERE payconfirmedat IS NOT NULL AND canceledat IS NULL) AS confirmed, count(1) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed, count(1) FILTER (WHERE canceledat IS NOT NULL) AS canceled FROM confreg_conferenceregistration WHERE conference_id=%(confid)s", {'confid': conference.id})[0],
        'breadcrumbs': (('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),),
        'helplink': 'registrations',
    })


def admin_registration_single(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)

    reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

    maxlogrows = 20

    if reg.attendee:
        sessions = ConferenceSession.objects.filter(conference=conference, speaker__user=reg.attendee)
    else:
        sessions = None
    return render(request, 'confreg/admin_registration_single.html', {
        'conference': conference,
        'reg': reg,
        'log': ConferenceRegistrationLog.objects.select_related('user').order_by('-ts').filter(reg=reg)[:maxlogrows + 1],
        'maxlogrows': maxlogrows,
        'sessions': sessions,
        'signups': _get_registration_signups(conference, reg),
        'breadcrumbs': (
            ('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),
            ('/events/admin/{0}/regdashboard/list/'.format(urlname), 'Registration list'),
        ),
        'helplink': 'registrations',
    })


def admin_registration_log(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)

    reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

    return render(request, 'confreg/admin_registration_log.html', {
        'conference': conference,
        'reg': reg,
        'log': ConferenceRegistrationLog.objects.select_related('user').order_by('-ts').filter(reg=reg),
        'breadcrumbs': (
            ('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),
            ('/events/admin/{0}/regdashboard/list/'.format(urlname), 'Registration list'),
            ('/events/admin/{0}/regdashboard/list/{1}/'.format(urlname, reg.id), 'Registration'),
        ),
        'helplink': 'registrations',
    })


@transaction.atomic
def admin_registration_cancel(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

    errs = list(_admin_registration_cancel_precheck([reg, ]))
    if errs:
        for r, e in errs:
            messages.warning(request, "{}: {}".format(r, e))
        return HttpResponseRedirect("../")
    return _admin_registration_cancel(request, conference, "../../", [reg, ])


@transaction.atomic
def admin_registration_multicancel(request, urlname):
    regids = request.GET.get('idlist')
    try:
        ids = [int(i) for i in regids.split(',')]
    except Exception:
        raise Http404("Parameter idlist is not list of integers")

    conference = get_authenticated_conference(request, urlname)
    regs = ConferenceRegistration.objects.filter(conference=conference, id__in=ids)

    errs = list(_admin_registration_cancel_precheck(regs))
    if errs:
        if len(errs) > 10:
            messages.warning(request, "Pre-check returned {} errors. Try with a smaller set.".format(len(e)))
        else:
            for r, e in errs:
                messages.warning(request, "{}: {}".format(r, e))
        return HttpResponseRedirect("../")

    return _admin_registration_cancel(request, conference, "../", regs)


def _admin_registration_cancel_precheck(regs):
    for reg in regs:
        if reg.canceledat:
            yield (reg, "Registration already canceled")
        elif (not reg.payconfirmedat) and reg.bulkpayment:
            yield (reg, "Registration part of a bulk payment, cannot be individually canceled")
        elif reg.pendingadditionalorder_set.exists():
            yield (reg, "Sorry, can't refund invoices that have post-purchased additional options yet")


class RegCancelException(Exception):
    def __init__(self, reg, message):
        self.reg = reg
        super().__init__(message)


def _admin_registration_cancel(request, conference, redirurl, regs):
    totalnovat = totalvat = 0

    regtotalvat = {}
    regtotalnovat = {}
    regtotalwithvat = {}

    for reg in regs:
        # Figure out the total cost paid
        if reg.payconfirmedat:
            if reg.invoice:
                _totalnovat = reg.invoice.total_amount - reg.invoice.total_vat
                _totalvat = reg.invoice.total_vat
            elif reg.bulkpayment:
                (_totalnovat, _totalvat) = attendee_cost_from_bulk_payment(reg)
            else:
                _totalvat = _totalnovat = 0
        else:
            # Not confirmed yet. By definition removable without refund.
            _totalvat = _totalnovat = 0

        regtotalvat[reg.id] = _totalvat
        regtotalnovat[reg.id] = _totalnovat
        regtotalwithvat[reg.id] = _totalnovat + _totalvat
        totalnovat += _totalnovat
        totalvat += _totalvat

    refundchoices = []
    if totalnovat:
        # If there is anything paid at all, build a set of refund patterns. If there wasn't,
        # we just allow cancel without refund.
        for pattern in RefundPattern.objects.filter(conference=conference).order_by(F('fromdate').asc(nulls_first=True), 'todate', 'percent'):
            # Apply this pattern to each registration in turn, to figure out the total cost.
            this_to_refund = Decimal(0)
            this_to_refund_vat = Decimal(0)
            this_to_refund_fees = Decimal(0)
            for rid in regtotalnovat.keys():
                if regtotalnovat[rid] <= 0:
                    # If there was no cost, also don't apply the fixed fee
                    continue

                this_to_refund += (regtotalnovat[rid] * pattern.percent / Decimal(100) - pattern.fees).quantize(Decimal('0.01'))
                if conference.vat_registrations:
                    this_to_refund_vat += (regtotalvat[rid] * pattern.percent / Decimal(100) - pattern.fees * conference.vat_registrations.vatpercent / Decimal(100)).quantize(Decimal('0.01'))

            today = today_conference()
            if (pattern.fromdate is None or pattern.fromdate <= today) and \
               (pattern.todate is None or pattern.todate >= today):
                suggest = "***"
            else:
                suggest = ""

            refundchoices.append((
                pattern.id,
                "{} Refund {}%{} ({}{}{}){}{} {}".format(
                    suggest,
                    pattern.percent,
                    pattern.fees and ' minus {0}{1} in fees'.format(settings.CURRENCY_SYMBOL, pattern.fees) or '',
                    settings.CURRENCY_SYMBOL,
                    this_to_refund,
                    this_to_refund_vat and ' +{}{} VAT'.format(settings.CURRENCY_SYMBOL, this_to_refund_vat) or '',
                    pattern.fromdate and ' from {0}'.format(pattern.fromdate) or '',
                    pattern.todate and ' until {0}'.format(pattern.todate) or '',
                    suggest,
                )
            ), )

    refundchoices.append((CancelRegistrationForm.Methods.NO_REFUND, 'Cancel without refund'), )

    if request.method == 'POST':
        form = CancelRegistrationForm(totalnovat, totalvat, refundchoices, data=request.POST)
        if form.is_valid():
            manager = InvoiceManager()
            method = int(form.cleaned_data['refund'])
            reason = form.cleaned_data['reason']
            if method >= 0:
                try:
                    pattern = RefundPattern.objects.get(conference=conference, pk=method)
                except RefundPattern.DoesNotExist:
                    raise Exception("Can't re-find registration pattern")
            else:
                pattern = None

            spoint = transaction.savepoint()
            try:
                # Loop over all registrations and cancel them one by one
                for reg in regs:
                    if method == form.Methods.NO_REFUND:
                        if reg.payconfirmedat:
                            # An invoice may exist, but in this case we don't want to provide
                            # a refund. This can only happen for registrations that are actually
                            # confirmed.
                            if reg.invoice:
                                reg.invoice = None
                                reg.save()
                                reglog(reg, "Unlinked from invoice for no refund cancellation", request.user)
                            elif reg.bulkpayment:
                                reg.bulkpayment = None
                                reg.save()
                                reglog(reg, "Unlinked from bulk payment for no refund cancellation", request.user)
                            elif reg.payconfirmedby not in ("no payment reqd", "Multireg/nopay") and not reg.payconfirmedby.startswith("Manual/"):
                                raise RegCancelException(reg, "Can't cancel this registration without refund")
                            cancel_registration(reg, False, reason=reason, user=request.user)
                        else:
                            # Payment is not confirmed yet, meaning we just need to get rid of
                            # an existing invoice if there is one.
                            if reg.invoice:
                                # We have an invoice, but it's not paid. OK, so just cancel it.
                                manager.cancel_invoice(reg.invoice, reason, request.user.username)
                            elif reg.bulkpayment:
                                # Part of a bulk payment -- can't get rid of that from here!
                                raise RegCancelException(reg, "Can't cancel when part of unpaid bulk payment")
                            # else there is no invoice, so we can just cancel/remove the registration.
                            cancel_registration(reg, True, reason=reason, user=request.user)
                    elif method >= 0:
                        # Refund using a pattern!
                        # Calculate amount to refund
                        to_refund = (regtotalnovat[reg.id] * pattern.percent / Decimal(100) - pattern.fees).quantize(Decimal('0.01'))
                        if conference.vat_registrations:
                            to_refund_vat = (regtotalvat[reg.id] * pattern.percent / Decimal(100) - pattern.fees * conference.vat_registrations.vatpercent / Decimal(100)).quantize(Decimal('0.01'))
                        else:
                            to_refund_vat = Decimal(0)

                        if reg.invoice:
                            invoice = reg.invoice
                        elif reg.bulkpayment:
                            invoice = reg.bulkpayment.invoice
                        else:
                            # No invoice. Just double check that this was supposed to be the case!
                            if reg.payconfirmedby not in ("no payment reqd", "Multireg/nopay") and not reg.payconfirmedby.startswith("Manual/"):
                                raise RegCancelException(reg, "Can't find which invoice to refund")
                            invoice = None

                        if invoice:
                            # If there is an invoice, go ahead and refund it
                            if to_refund < 0 or to_refund_vat < 0:
                                raise RegCancelException(reg, "Selected pattern would lead to negative refunding, can't refund.")
                            elif to_refund > invoice.total_refunds['remaining']['amount']:
                                raise RegCancelException(reg, "Attempt to refund {0}, which is more than remaing {1}".format(to_refund, invoice.total_refunds['remaining']['amount']))
                            elif to_refund_vat > invoice.total_refunds['remaining']['vatamount']:
                                raise RegCancelException(reg, "Attempt to refund VAT {0}, which is more than remaining {1}".format(to_refund_vat, invoice.total_refunds['remaining']['vatamount']))
                            else:
                                # OK, looks good. Start by refunding the invoice.
                                manager.refund_invoice(invoice, reason, to_refund, to_refund_vat, conference.vat_registrations)

                        # Then cancel the actual registration (regardless of invoice)
                        cancel_registration(reg, reason=reason, user=request.user)
                    else:
                        raise RegCancelException(reg, "Don't know how to cancel like that")

                messages.info(request, "{} registrations canceled".format(len(regs)))
                transaction.savepoint_commit(spoint)
                return HttpResponseRedirect(redirurl)
            except RegCancelException as rce:
                form.add_error(None, "Registration {}: {}".format(rce.reg, str(rce)))
                transaction.savepoint_rollback(spoint)
    else:
        form = CancelRegistrationForm(totalnovat, totalvat, refundchoices)

    if len(regs) == 1:
        extracrumbs = [
            ('/events/admin/{0}/regdashboard/list/{1}/'.format(conference.urlname, regs[0].id), regs[0].fullname),
        ]
    else:
        extracrumbs = []

    return render(request, 'confreg/admin_registration_cancel.html', {
        'conference': conference,
        'regs': regs,
        'form': form,
        'totalnovat': totalnovat,
        'totalvat': totalvat,
        'totalwithvat': totalnovat + totalvat,
        'regtotalvat': regtotalvat,
        'regtotalnovat': regtotalnovat,
        'regtotalwithvat': regtotalwithvat,
        'regidlist': ",".join([str(r.id) for r in regs]),
        'helplink': 'registrations',
        'breadcrumbs': [
            ('/events/admin/{0}/regdashboard/'.format(conference.urlname), 'Registration dashboard'),
            ('/events/admin/{0}/regdashboard/list/'.format(conference.urlname), 'Registration list'),
        ] + extracrumbs,
    })


@transaction.atomic
def admin_registration_confirm(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

    if reg.payconfirmedat:
        messages.error(request, "Registration already confirmed")
        return HttpResponseRedirect("../")
    if reg.canceledat:
        messages.error(request, "Registration is canceled")
        return HttpResponseRedirect("../")
    if not reg.can_edit:
        messages.error(request, "Cannot confirm a registration with active invoice or multireg")
        return HttpResponseRedirect("../")
    if not reg.regtype:
        messages.error(request, "Cannot confirm a registration without a registration type!")
        return HttpResponseRedirect("../")

    if request.method == 'POST':
        form = ConfirmRegistrationForm(data=request.POST)
        if form.is_valid():
            reg.payconfirmedat = timezone.now()
            reg.payconfirmedby = "Manual/{0}".format(request.user.username)[:16]
            reg.save()
            reglog(reg, "Manually confirmed registration", request.user)
            notify_reg_confirmed(reg)
            messages.info(request, "Registration marked confirmed.")
            return HttpResponseRedirect("../")
    else:
        form = ConfirmRegistrationForm()

    return render(request, 'confreg/admin_backend_form.html', {
        'basetemplate': 'confreg/confadmin_base.html',
        'conference': conference,
        'reg': reg,
        'form': form,
        'helplink': 'registrations',
        'breadcrumbs': (
            ('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),
            ('/events/admin/{0}/regdashboard/list/'.format(urlname), 'Registration list'),
            ('/events/admin/{0}/regdashboard/list/{1}/'.format(urlname, reg.id), reg.fullname),
        ),
        'whatverb': 'Confirm',
        'what': 'registration',
        'cancelurl': '../',
        'savebutton': 'Confirm registration',
    })


@transaction.atomic
def admin_registration_resendwelcome(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

    if not reg.payconfirmedat:
        messages.error(request, "Registration not confirmed")
        return HttpResponseRedirect("../")

    if reg.canceledat:
        messages.error(request, "Registration is canceled")
        return HttpResponseRedirect("../")

    if request.method == 'POST':
        form = ResendWelcomeMailForm(data=request.POST)
        if form.is_valid():
            send_welcome_email(reg)
            messages.info(request, "Welcome email re-sent.")
            return HttpResponseRedirect("../")
    else:
        form = ResendWelcomeMailForm()

    return render(request, 'confreg/admin_backend_form.html', {
        'basetemplate': 'confreg/confadmin_base.html',
        'conference': conference,
        'reg': reg,
        'form': form,
        'helplink': 'registrations',
        'breadcrumbs': (
            ('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),
            ('/events/admin/{0}/regdashboard/list/'.format(urlname), 'Registration list'),
            ('/events/admin/{0}/regdashboard/list/{1}/'.format(urlname, reg.id), reg.fullname),
        ),
        'whatverb': 'Re-send',
        'what': 'welcome email',
        'cancelurl': '../',
        'savebutton': 'Re-send welcome email',
    })


@transaction.atomic
def admin_registration_clearcode(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)

    reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)
    if reg.has_invoice():
        messages.warning(request, "Cannot clear the code from a registration with an invoice")
    else:
        messages.info(request, "Removed voucher code '{0}'".format(reg.vouchercode))
        reg.vouchercode = ""
        reglog(reg, "Removed voucher code", request.user)
        reg.save()
    return HttpResponseRedirect("../")


@transaction.atomic
def admin_waitlist(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    if conference.attendees_before_waitlist <= 0:
        return render(request, 'confreg/admin_waitlist_inactive.html', {
            'conference': conference,
            'helplink': 'waitlist',
            })

    def _waitlist_paginate(objs, objtype):
        num = len(objs)
        p = paginator.Paginator(objs, 20)
        p.varsuffix = objtype
        try:
            page = get_int_or_error(request.GET, "page_{0}".format(objtype), 1)
        except ValueError:
            page = 1
        try:
            return p.page(page), num
        except (paginator.EmptyPage, paginstor.InvalidPage):
            return p.page(paginator.num_pages), num

    num_confirmedregs = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True).count()
    num_invoicedregs = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=True, invoice__isnull=False, registrationwaitlistentry__isnull=True).count()
    num_invoicedbulkpayregs = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=True, bulkpayment__isnull=False, bulkpayment__paidat__isnull=True).count()
    num_waitlist_offered = RegistrationWaitlistEntry.objects.filter(registration__conference=conference, offeredon__isnull=False, registration__payconfirmedat__isnull=True).count()
    waitlist, num_waitlist = _waitlist_paginate(RegistrationWaitlistEntry.objects.filter(registration__conference=conference, registration__payconfirmedat__isnull=True).order_by('enteredon'), 'w')
    waitlist_cleared, num_waitlist_cleared = _waitlist_paginate(RegistrationWaitlistEntry.objects.filter(registration__conference=conference, registration__payconfirmedat__isnull=False).order_by('-registration__payconfirmedat', 'enteredon'), 'cl')

    if request.method == 'POST':
        # Attempting to make an offer
        form = WaitlistOfferForm(data=request.POST)
        if form.is_valid():
            regs = ConferenceRegistration.objects.filter(conference=conference, id__in=form.reg_list)
            if len(regs) != len(form.reg_list):
                raise Exception("Database lookup mismatch")
            if len(regs) < 1:
                raise Exception("Somehow got through with zero!")

            for r in regs:
                wl = r.registrationwaitlistentry
                if wl.offeredon:
                    raise Exception("One or more already offered!")
                wl.offeredon = timezone.now()
                if request.POST.get('submit') == 'Make offer for hours':
                    wl.offerexpires = timezone.now() + timedelta(hours=form.cleaned_data['hours'])
                    RegistrationWaitlistHistory(waitlist=wl,
                                                text="Made offer valid for {0} hours by {1}".format(form.cleaned_data['hours'], request.user.username)).save()
                else:
                    wl.offerexpires = form.cleaned_data['until']
                    RegistrationWaitlistHistory(waitlist=wl,
                                                text="Made offer valid until {0} by {1}".format(form.cleaned_data['until'], request.user.username)).save()
                wl.save()
                send_conference_mail(conference,
                                     r.email,
                                     "Your waitlisted registration",
                                     'confreg/mail/waitlist_offer.txt',
                                     {
                                         'conference': conference,
                                         'reg': r,
                                         'offerexpires': wl.offerexpires,
                                     },
                                     receivername=r.fullname,
                )
                messages.info(request, "Sent offer to {0}".format(r.email))
            return HttpResponseRedirect(".")
    else:
        form = WaitlistOfferForm()

    return render(request, 'confreg/admin_waitlist.html', {
        'conference': conference,
        'num_confirmedregs': num_confirmedregs,
        'num_invoicedregs': num_invoicedregs,
        'num_invoicedbulkpayregs': num_invoicedbulkpayregs,
        'num_waitlist_offered': num_waitlist_offered,
        'num_waitlist': num_waitlist,
        'num_waitlist_cleared': num_waitlist_cleared,
        'num_total': num_confirmedregs + num_invoicedregs + num_invoicedbulkpayregs + num_waitlist_offered,
        'waitlist': waitlist,
        'waitlist_cleared': waitlist_cleared,
        'form': form,
        'helplink': 'waitlist',
        })


@transaction.atomic
def admin_waitlist_cancel(request, urlname, wlid):
    conference = get_authenticated_conference(request, urlname)

    wl = get_object_or_404(RegistrationWaitlistEntry, pk=wlid, registration__conference=conference)
    reg = wl.registration
    if wl.offeredon:
        # Active offer means we are moving this entry back onto the waitlist
        RegistrationWaitlistHistory(waitlist=wl,
                                    text="Offer canceled by {0}".format(request.user.username)).save()
        wl.offeredon = None
        wl.offerexpires = None
        wl.enteredon = timezone.now()
        wl.save()

        send_conferece_notification(
            reg.conference,
            'Waitlist offer cancel',
            'Waitlist offer for user {0} {1} <{2}> canceled by {3}. User remains on waitlist.'.format(reg.firstname, reg.lastname, reg.email, request.user),
        )

        send_conference_mail(reg.conference,
                             reg.email,
                             'Waitlist offer canceled',
                             'confreg/mail/waitlist_admin_offer_cancel.txt',
                             {
                                 'conference': conference,
                                 'reg': reg,
                             },
                             receivername=reg.fullname,
        )
        messages.info(request, "Waitlist offer canceled.")

    else:
        # No active offer means we are canceling the entry completely
        wl.delete()

        send_conference_notification(
            reg.conference,
            'Waitlist cancel',
            'User {0} {1} <{2}> removed from the waitlist by {3}.'.format(reg.firstname, reg.lastname, reg.email, request.user),
        )

        send_conference_mail(reg.conference,
                             reg.email,
                             'Waitlist canceled',
                             'confreg/mail/waitlist_admin_cancel.txt',
                             {
                                 'conference': conference,
                                 'reg': reg,
                             },
                             receivername=reg.fullname,
        )

        messages.info(request, "Waitlist entry removed.")
    return HttpResponseRedirect("../../")


def admin_waitlist_sendmail(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    if request.method == 'POST':
        form = WaitlistSendmailForm(conference, data=request.POST)
        if form.is_valid():
            with transaction.atomic():
                q = RegistrationWaitlistEntry.objects.filter(registration__conference=conference,
                                                             registration__payconfirmedat__isnull=True)
                tot = q.all().count()
                if not tot:
                    messages.warning(request, "Waitlist was empty, no email was sent.")
                    return HttpResponseRedirect('../')

                if int(form.cleaned_data['waitlist_target']) == form.TARGET_OFFERS:
                    q = q.filter(offeredon__isnull=False)
                elif int(form.cleaned_data['waitlist_target']) == form.TARGET_NOOFFERS:
                    q = q.filter(offeredon__isnull=True)

                n = 0
                for w in q.order_by('enteredon'):
                    n += 1

                    msgbody = form.cleaned_data['message']
                    if int(form.cleaned_data['include_position']) == form.POSITION_FULL:
                        positioninfo = "Your position on the waitlist is {0} of {1}.".format(n, tot)
                    elif int(form.cleaned_data['include_position']) == form.POSITION_ONLY:
                        positioninfo = "Your position on the waitlist is {0}.".format(n)
                    elif int(form.cleaned_data['include_position']) == form.POSITION_SIZE:
                        positioninfo = "The current size of the waitlist is {0}.".format(tot)
                    else:
                        positioninfo = None

                    send_conference_mail(conference,
                                         w.registration.email,
                                         form.cleaned_data['subject'],
                                         'confreg/mail/waitlist_manual_mail.txt',
                                         {
                                             'body': msgbody,
                                             'positioninfo': positioninfo,
                                         },
                                         receivername=w.registration.fullname,
                    )
                if n:
                    messages.info(request, "Sent {0} emails.".format(tot))
                else:
                    messages.warning(request, "No matching waitlist entries, no email was sent.")
                return HttpResponseRedirect('../')
    else:
        form = WaitlistSendmailForm(conference)

    return render(request, 'confreg/admin_waitlist_sendmail.html', {
        'conference': conference,
        'form': form,
        'helplink': 'waitlist#emails',
        'breadcrumbs': (('/events/admin/{0}/waitlist/'.format(conference.urlname), 'Waitlist'),),
    })


@transaction.atomic
def admin_attendeemail(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    mails = AttendeeMail.objects.filter(conference=conference)

    if request.method == 'POST':
        form = AttendeeMailForm(conference, data=request.POST)
        if form.is_valid():
            msg = AttendeeMail(conference=conference,
                               subject=form.data['subject'],
                               message=form.data['message'],
                               tovolunteers='tovolunteers' in form.data,
                               tocheckin='tocheckin' in form.data,
            )
            msg.save()
            for rc in form.data.getlist('regclasses'):
                msg.regclasses.add(rc)
            for ao in form.data.getlist('addopts'):
                msg.addopts.add(ao)
            msg.save()

            # Now also send the email out to the currently registered attendees
            attendees = set(ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, regtype__regclass__in=form.data.getlist('regclasses')))
            if form.data.getlist('addopts'):
                attendees.update(ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, additionaloptions__in=form.data.getlist('addopts')))
            if msg.tovolunteers:
                attendees.update(conference.volunteers.all())
            if msg.tocheckin:
                attendees.update(conference.checkinprocessors.all())

            for a in attendees:
                send_conference_mail(conference,
                                     a.email,
                                     msg.subject,
                                     'confreg/mail/attendee_mail.txt',
                                     {
                                         'body': msg.message,
                                         'linkback': True,
                                     },
                                     receivername=a.fullname,
                )
            messages.info(request, "Email sent to %s attendees, and added to their registration pages" % len(attendees))
            return HttpResponseRedirect(".")
    else:
        form = AttendeeMailForm(conference)

    return render(request, 'confreg/admin_mail.html', {
        'conference': conference,
        'mails': mails,
        'form': form,
        'helplink': 'emails',
    })


def admin_attendeemail_view(request, urlname, mailid):
    conference = get_authenticated_conference(request, urlname)

    mail = get_object_or_404(AttendeeMail, conference=conference, pk=mailid)

    return render(request, 'confreg/admin_mail_view.html', {
        'conference': conference,
        'mail': mail,
        'breadcrumbs': (('/events/admin/{0}/mail/'.format(conference.urlname), 'Attendee emails'), ),
        'helplink': 'emails',
        })


@transaction.atomic
def session_notify_queue(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    notifysessions = ConferenceSession.objects.filter(conference=conference).exclude(status=F('lastnotifiedstatus')).exclude(speaker__isnull=True)

    if request.method == 'POST' and request.POST.get('confirm_sending', 0) == '1':
        # Ok, it would appear we should actually send them...
        num = 0
        for s in notifysessions:
            for spk in s.speaker.all():
                send_conference_mail(conference,
                                     spk.user.email,
                                     "Your session '{0}'".format(s.title),
                                     'confreg/mail/session_notify_{0}.txt'.format(s.status_string_short),
                                     {
                                         'conference': conference,
                                         'session': s,
                                     },
                                     receivername=spk.fullname,
                )
                num += 1
            s.lastnotifiedstatus = s.status
            s.lastnotifiedtime = timezone.now()
            s.save()
        messages.info(request, 'Sent email to %s recipients, for %s sessions' % (num, len(notifysessions)))
        return HttpResponseRedirect('.')

    return render(request, 'confreg/admin_session_queue.html', {
        'conference': conference,
        'notifysessions': notifysessions,
        })


@transaction.atomic
def transfer_reg(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    def _make_transfer(fromreg, toreg):
        yield "Initiating transfer from %s to %s" % (fromreg.fullname, toreg.fullname)
        if fromreg.canceledat:
            raise ValidationError("Source registration is canceled!")
        if toreg.payconfirmedat:
            raise ValidationError("Destination registration is already confirmed!")
        if toreg.canceledat:
            raise ValidationError("Destination registration is canceled!")
        if toreg.bulkpayment:
            raise ValidationError("Destination registration is part of a bulk payment")
        if toreg.invoice:
            raise ValidationError("Destination registration has an invoice")

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

        # Invoice?
        if fromreg.invoice:
            yield "Transferring invoice %s" % fromreg.invoice.id
            toreg.invoice = fromreg.invoice
            fromreg.invoice = None
            InvoiceHistory(invoice=toreg.invoice,
                           txt="Transferred from {0} to {1}".format(fromreg.email, toreg.email)
                           ).save()

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
        reglog(toreg, "Transfered registration from {}".format(fromreg.user.username), request.user)

        yield "Sending notification to target registration"
        notify_reg_confirmed(toreg, False)

        yield "Sending notification to source registration"
        send_conference_mail(fromreg.conference,
                             fromreg.email,
                             "Registration transferred",
                             'confreg/mail/reg_transferred.txt', {
                                 'conference': conference,
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

    steps = None
    stephash = None
    if request.method == 'POST':
        form = TransferRegForm(conference, data=request.POST)
        if form.is_valid():
            savepoint = transaction.savepoint()
            try:
                steps = list(_make_transfer(form.cleaned_data['transfer_from'],
                                            form.cleaned_data['transfer_to'],
                                            ))
            except ValidationError as e:
                form.add_error(None, e)
                form.remove_confirm()

            if steps:
                sh = SHA256.new()
                for s in steps:
                    sh.update(s.encode('utf8'))
                stephash = sh.hexdigest()

            if form.cleaned_data['confirm']:
                if stephash != request.POST.get('stephash', None):
                    messages.error(request, 'Something changed while running. Start over!')
                    transaction.set_rollback(True)
                    return HttpResponseRedirect('.')
                transaction.savepoint_commit(savepoint)
                messages.info(request, "Registration transfer completed.")
                return HttpResponseRedirect('../')
            else:
                transaction.savepoint_rollback(savepoint)

            # Fall through!
    else:
        form = TransferRegForm(conference)

    return render(request, 'confreg/admin_transfer.html', {
        'conference': conference,
        'form': form,
        'steps': steps,
        'stephash': stephash,
        'helplink': 'registrations#transfer',
    })


# Send email to attendees of mixed conferences
@login_required
def crossmail(request):
    if not (request.user.is_superuser or ConferenceSeries.objects.filter(administrators=request.user).exists()):
        return HttpResponseForbidden()

    if request.user.is_superuser:
        emails = CrossConferenceEmail.objects.all()
    else:
        emails = CrossConferenceEmail.objects.filter(sentby=request.user)
    email_objects = emails.order_by('-sentat')

    (emails, paginator, page_range) = simple_pagination(request, email_objects, 25)

    return render(request, 'confreg/admin_cross_conference.html', {
        'emails': emails,
        'page_range': page_range,
        'helplink': 'emails#crossconference',
    })


@login_required
def crossmail_view(request, mailid):
    if not (request.user.is_superuser or ConferenceSeries.objects.filter(administrators=request.user).exists()):
        return HttpResponseForbidden()

    if request.user.is_superuser:
        email = get_object_or_404(CrossConferenceEmail, pk=mailid)
    else:
        email = get_object_or_404(CrossConferenceEmail, pk=mailid, sentby=request.user)

    return render(request, 'confreg/admin_cross_conference_view.html', {
        'email': email,
        'recipients': CrossConferenceEmailRecipient.objects.filter(email=email).order_by('address'),
        'breadcrumbs': [
            ('/events/admin/crossmail/', 'Cross conference email'),
        ],
        'helplink': 'emails#crossconference',
    })


@login_required
@transaction.atomic
def crossmail_send(request):
    if not (request.user.is_superuser or ConferenceSeries.objects.filter(administrators=request.user).exists()):
        return HttpResponseForbidden()

    if request.user.is_superuser:
        conferences = list(Conference.objects.all())
    else:
        conferences = list(Conference.objects.filter(series__administrators=request.user))
    conferenceids = set((c.id for c in conferences))

    def _get_recipients_for_crossmail(postdict):
        def _get_one_filter(conf, filt, optout_filter=False):
            conf = int(conf)
            if conf not in conferenceids:
                raise ValidationError("Invalid conference selected")

            (t, v, c) = filt.split(':')
            c = c == "1"
            if t == 'rt':
                # Regtype
                q = "SELECT attendee_id, email, firstname || ' ' || lastname, regtoken FROM confreg_conferenceregistration WHERE conference_id={0} AND payconfirmedat IS NOT NULL".format(conf)
                if v != '-1':
                    q += ' AND regtype_id={0}'.format(int(v))
                if not c:
                    # Exclude canceled registrations
                    q += ' AND canceledat IS NULL'
                if optout_filter:
                    q += " AND NOT EXISTS (SELECT 1 FROM confreg_conferenceseriesoptout INNER JOIN confreg_conference ON confreg_conference.series_id=confreg_conferenceseriesoptout.series_id WHERE user_id=attendee_id AND confreg_conference.id={0})".format(int(conf))
            elif t == 'sp':
                # Speaker
                if v == '-1':
                    sf = ""
                elif v == '-2':
                    sf = " AND status IN (1,3)"
                else:
                    sf = " AND status = {0}".format(int(v))

                q = "SELECT user_id, email, fullname, speakertoken FROM confreg_speaker INNER JOIN auth_user ON auth_user.id=confreg_speaker.user_id WHERE EXISTS (SELECT 1 FROM confreg_conferencesession_speaker INNER JOIN confreg_conferencesession ON confreg_conferencesession.id=conferencesession_id WHERE speaker_id=confreg_speaker.id AND conference_id={0}{1})".format(conf, sf)
                if optout_filter:
                    q += " AND NOT EXISTS (SELECT 1 FROM confreg_conferenceseriesoptout INNER JOIN confreg_conference ON confreg_conference.series_id=confreg_conferenceseriesoptout.series_id WHERE confreg_conferenceseriesoptout.user_id=confreg_speaker.user_id AND confreg_conference.id={0})".format(int(conf))
            else:
                raise Exception("Invalid filter type")
            return q

        if postdict['include'] == '':
            return []

        # Parse all includes and excludes
        incs = [_get_one_filter(*i.split('@'), optout_filter=True) for i in postdict['include'].split(';') if i != '']
        excs = [_get_one_filter(*i.split('@')) for i in postdict['exclude'].split(';') if i != '']

        q = StringIO()
        q.write("WITH incs (userid, email, fullname, token) AS (")
        q.write("\nUNION ALL\n".join(incs))
        q.write("\n)")
        if excs:
            q.write(", excs (userid, email, fullname, token) AS (\n")
            q.write("\nUNION ALL\n".join(excs))
            q.write("\n)\n")
        q.write("SELECT DISTINCT ON (email) email, fullname, token FROM incs\n")
        q.write(" WHERE (userid IS NULL OR userid NOT IN (SELECT user_id FROM confreg_globaloptout))\n")
        if excs:
            q.write(" and email NOT IN (SELECT email FROM excs)\n")
        q.write("ORDER BY email")

        return exec_to_dict(q.getvalue())

    if request.method == 'POST':
        form = CrossConferenceMailForm(request.user, data=request.POST)

        try:
            recipients = _get_recipients_for_crossmail(request.POST)
        except ValidationError as e:
            form.add_error(None, e)
            form.remove_confirm()
            recipients = None

        if form.is_valid() and recipients:
            # Store the email itself and all the recipients
            def _addrule(email, ruledef, isexclude):
                (confid, parts) = ruledef.split('@')
                (t, ref, canc) = parts.split(':')
                CrossConferenceEmailRule(
                    email=email,
                    conference=Conference.objects.get(pk=confid),
                    isexclude=isexclude,
                    ruletype=t,
                    ruleref=ref,
                    canceled=canc,
                ).save()

            email = CrossConferenceEmail(
                sentby=request.user,
                senderaddr=form.data['senderaddr'],
                sendername=form.data['sendername'],
                subject=form.data['subject'],
                text=form.data['text'],
            )
            email.save()

            for r in request.POST['include'].split(';'):
                if r:
                    _addrule(email, r, False)
            for r in request.POST['exclude'].split(';'):
                if r:
                    _addrule(email, r, True)

            for r in recipients:
                CrossConferenceEmailRecipient(email=email, address=r['email']).save()

                send_simple_mail(form.data['senderaddr'],
                                 r['email'],
                                 form.data['subject'],
                                 "{0}\n\n\nThis email was sent to you from {1}.\nTo opt-out from further communications about our events, please fill out the form at:\n{2}/events/optout/{3}/".format(form.data['text'], settings.ORG_NAME, settings.SITEBASE, r['token']),
                                 sendername=form.data['sendername'],
                                 receivername=r['fullname'],
                )

            messages.info(request, "Sent {0} emails.".format(len(recipients)))
            return HttpResponseRedirect("../")
        if not recipients:
            if recipients is not None:
                form.add_error(None, "No recipients matched")
            form.remove_confirm()
    else:
        form = CrossConferenceMailForm(request.user)
        recipients = None

    return render(request, 'confreg/admin_cross_conference_mail.html', {
        'form': form,
        'recipients': recipients,
        'conferences': conferences,
        'helplink': 'emails#crossconference',
        'breadcrumbs': [
            ('/events/admin/crossmail/', 'Cross conference email'),
        ],
    })


@login_required
@transaction.atomic
def crossmailoptions(request):
    if 'conf' not in request.GET:
        raise Http404("No conf")

    if not (request.user.is_superuser or ConferenceSeries.objects.filter(administrators=request.user).exists()):
        return HttpResponseForbidden()

    if request.GET['conf'] == '-1':
        # Requesting a list of conferences
        if request.user.is_superuser:
            conferences = list(Conference.objects.all())
        else:
            conferences = list(Conference.objects.filter(series__administrators=request.user))

        return HttpResponse(json.dumps([
            {'id': c.id, 'title': str(c)}
            for c in conferences]
        ), content_type="application/json")

    # We can safely get the conference directly here, since we won't be using any
    # date/time information and thus don't need the timezone to be set.
    conf = get_object_or_404(Conference, id=get_int_or_error(request.GET, 'conf'))
    if not request.user.is_superuser:
        # Need to verify conference series permissions for non-superuser
        if not conf.series.administrators.filter(pk=request.user.id).exists():
            return HttpResponseForbidden()

    # Get a list of different crossmail options for this conference. Note that
    # each of them must have an implementation in _get_one_filter() or bad things
    # will happen.
    r = [
        {'id': 'rt:-1', 'title': 'Reg: all'},
    ]
    r.extend([
        {'id': 'rt:{0}'.format(rt.id), 'title': 'Reg: {0}'.format(rt.regtype)}
        for rt in RegistrationType.objects.filter(conference=conf)])
    r.extend([
        {'id': 'sp:-1', 'title': 'Speaker: all'},
        {'id': 'sp:-2', 'title': 'Speaker: accept+reserve'},
    ])
    r.extend([
        {'id': 'sp:{0}'.format(k), 'title': 'Speaker: {0}'.format(v)}
        for k, v in STATUS_CHOICES
    ])
    return HttpResponse(json.dumps(r), content_type="application/json")


# Redirect from old style event URLs
def legacy_redirect(request, what, confname, resturl=None):
    # Fallback to most basic syntax
    if resturl:
        return HttpResponsePermanentRedirect('/events/{0}/{1}/{2}'.format(confname, what, resturl))
    else:
        return HttpResponsePermanentRedirect('/events/{0}/{1}/'.format(confname, what))
