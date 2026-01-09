from django.shortcuts import render, get_object_or_404
from django.db import transaction, connection
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

import csv
import io
import json
from collections import OrderedDict

from postgresqleu.util.db import exec_to_list, exec_to_dict, exec_no_result, exec_to_scalar
from postgresqleu.util.decorators import superuser_required
from postgresqleu.util.messaging import messaging_implementations, get_messaging_class
from postgresqleu.util.messaging.util import send_reg_direct_message
from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.util.jsonutil import JsonSerializer
from postgresqleu.confreg.util import get_authenticated_conference, get_authenticated_series
from postgresqleu.util.request import get_int_or_error

from .jinjafunc import JINJA_TEMPLATE_ROOT
from .jinjapdf import render_jinja_ticket, render_jinja_badges
from .util import get_conference_or_404, send_conference_notification

from .models import Conference, ConferenceSeries, ConferenceSession
from .models import ConferenceRegistration
from .models import Speaker
from .models import PrepaidBatch
from .models import BulkPayment
from .models import AccessToken
from .models import ShirtSize
from .models import PendingAdditionalOrder
from .models import ConferenceTweetQueue
from .models import MessagingProvider
from .models import RefundPattern

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.confsponsor.util import get_sponsor_dashboard_data
from postgresqleu.confsponsor.util import sponsorleveldata, sponsorclaimsdata, sponsorclaimsfile
from postgresqleu.confsponsor.models import PurchasedVoucher, Sponsor

from .backendforms import BackendConferenceForm, BackendSuperConferenceForm, BackendRegistrationForm
from .backendforms import BackendRegistrationTypeForm, BackendRegistrationClassForm
from .backendforms import BackendRegistrationDayForm, BackendAdditionalOptionForm
from .backendforms import BackendTrackForm, BackendRoomForm, BackendConferenceSessionForm
from .backendforms import BackendConferenceSpeakerForm, BackendGlobalSpeakerForm, BackendTagForm
from .backendforms import BackendConferenceSessionSlotForm, BackendVolunteerSlotForm
from .backendforms import BackendFeedbackQuestionForm, BackendDiscountCodeForm
from .backendforms import BackendAccessTokenForm
from .backendforms import BackendConferenceSeriesForm
from .backendforms import BackendTshirtSizeForm
from .backendforms import BackendNewsForm
from .backendforms import BackendTweetQueueForm, BackendHashtagForm
from .backendforms import TweetCampaignSelectForm
from .backendforms import BackendRefundPatternForm
from .backendforms import ConferenceInvoiceCancelForm
from .backendforms import PurchasedVoucherRefundForm
from .backendforms import BulkPaymentRefundForm
from .backendforms import BackendMessagingForm
from .backendforms import BackendSeriesMessagingForm
from .backendforms import BackendRegistrationDmForm
from .backendforms import BackendMergeSpeakerForm
from .mail import attendee_email_form, BaseAttendeeEmailProvider, AttendeeEmailQuerySampleMixin
from .contextutil import has_yaml

from .views import _scheduledata

from .campaigns import get_campaign_from_id


#######################
# Simple editing views
#######################
def edit_conference(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return backend_process_form(request,
                                urlname,
                                BackendConferenceForm,
                                conference.pk,
                                conference=conference,
                                bypass_conference_filter=True,
                                allow_new=False,
                                allow_delete=False)


@superuser_required
def superedit_conference(request, urlname):
    if not request.user.is_superuser:
        raise PermissionDenied("Superuser only")
    conference = get_conference_or_404(urlname)

    return backend_process_form(request,
                                urlname,
                                BackendSuperConferenceForm,
                                conference.pk,
                                conference=conference,
                                bypass_conference_filter=True,
                                allow_new=False,
                                allow_delete=False)


@superuser_required
def edit_series(request, rest):
    return backend_list_editor(request,
                               None,
                               BackendConferenceSeriesForm,
                               rest,
                               allow_new=True,
                               allow_delete=True,
                               bypass_conference_filter=True,
                               return_url='../../',
                               instancemaker=lambda: ConferenceSeries(),
    )


@superuser_required
def edit_tshirts(request, rest):
    return backend_list_editor(request,
                               None,
                               BackendTshirtSizeForm,
                               rest,
                               allow_new=True,
                               allow_delete=True,
                               bypass_conference_filter=True,
                               return_url='../../',
                               instancemaker=lambda: ShirtSize(),
    )


@superuser_required
def new_conference(request):
    return backend_process_form(request,
                                None,
                                BackendSuperConferenceForm,
                                None,
                                bypass_conference_filter=True,
                                allow_new=True,
                                allow_delete=False,
                                conference=Conference(),
                                instancemaker=lambda: Conference(),
    )


def edit_registration(request, urlname, regid):
    reg = get_object_or_404(ConferenceRegistration.objects.only('firstname', 'lastname').filter(conference__urlname=urlname, pk=regid))
    return backend_process_form(request,
                                urlname,
                                BackendRegistrationForm,
                                regid,
                                allow_new=False,
                                breadcrumbs=(
                                    ('/events/admin/{}/regdashboard/'.format(urlname), 'Registration dashboard'),
                                    ('/events/admin/{}/regdashboard/list/'.format(urlname), 'Registration list'),
                                    ('/events/admin/{}/regdashboard/list/{}/'.format(urlname, regid), reg.fullname),
                                ),
                                allow_delete=False)


def edit_regclasses(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendRegistrationClassForm,
                               rest)


def edit_regtypes(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendRegistrationTypeForm,
                               rest)


def edit_refundpatterns(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendRefundPatternForm,
                               rest)


def edit_regdays(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendRegistrationDayForm,
                               rest)


def edit_additionaloptions(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendAdditionalOptionForm,
                               rest)


def edit_tracks(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendTrackForm,
                               rest)


def edit_rooms(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendRoomForm,
                               rest)


def edit_tags(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendTagForm,
                               rest)


def edit_sessions(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendConferenceSessionForm,
                               rest)


def edit_speakers(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendConferenceSpeakerForm,
                               rest,
                               allow_new=True,
                               allow_delete=False,
                               instancemaker=lambda: Speaker(),
    )


@superuser_required
def edit_global_speakers(request, rest):
    return backend_list_editor(request,
                               None,
                               BackendGlobalSpeakerForm,
                               rest,
                               allow_new=True,
                               allow_delete=True,
                               bypass_conference_filter=True,
    )


def edit_scheduleslots(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendConferenceSessionSlotForm,
                               rest)


def edit_volunteerslots(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendVolunteerSlotForm,
                               rest)


def edit_feedbackquestions(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendFeedbackQuestionForm,
                               rest)


def edit_discountcodes(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendDiscountCodeForm,
                               rest)


def edit_accesstokens(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendAccessTokenForm,
                               rest)


def edit_news(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendNewsForm,
                               rest)


def edit_tweetqueue(request, urlname, rest):
    conference = get_authenticated_conference(request, urlname)

    return backend_list_editor(request,
                               urlname,
                               BackendTweetQueueForm,
                               rest,
                               return_url='../../',
                               instancemaker=lambda: ConferenceTweetQueue(conference=conference, author=request.user, add_initial_hashtags=True)
    )


def edit_hashtags(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendHashtagForm,
                               rest,
                               return_url='../../',
    )


def edit_messaging(request, urlname, rest):
    conference = get_authenticated_conference(request, urlname)
    # How about this for ugly :) Make sure this conference has an instance for every
    # available messaging on the series.
    with connection.cursor() as curs:
        curs.execute(
            """INSERT INTO confreg_conferencemessaging (conference_id, provider_id, broadcast, privatebcast, notification, orgnotification, socialmediamanagement, config)
SELECT %(confid)s, id, false, false, false, false, false, '{}'
FROM confreg_messagingprovider mp
WHERE mp.series_id=%(seriesid)s AND NOT EXISTS (
 SELECT 1 FROM confreg_conferencemessaging m2 WHERE m2.conference_id=%(confid)s AND m2.provider_id=mp.id
)""",
            {
                'confid': conference.id,
                'seriesid': conference.series_id,
            })

    return backend_list_editor(request,
                               urlname,
                               BackendMessagingForm,
                               rest,
                               conference=conference,
                               allow_new=False,
                               allow_delete=False,
    )


def edit_series_messaging(request, seriesid, rest):
    series = get_authenticated_series(request, seriesid)

    def _load_messaging_formclass(classname):
        return getattr(get_messaging_class(classname), 'provider_form_class', BackendSeriesMessagingForm)

    formclass = BackendSeriesMessagingForm
    u = rest and rest.rstrip('/') or rest
    if u and u != '' and u.isdigit():
        # Editing an existing one, so pick the correct subclass!
        provider = get_object_or_404(MessagingProvider, pk=u, series=series)
        formclass = _load_messaging_formclass(provider.classname)
    elif u == 'new':
        if '_newformdata' in request.POST or 'classname' in request.POST:
            if '_newformdata' in request.POST:
                c = request.POST['_newformdata'].split(':')[0]
            else:
                c = request.POST['classname']

            if c not in messaging_implementations:
                raise PermissionDenied()

            formclass = _load_messaging_formclass(c)

    # Note! Sync with newsevents/backendviews.py
    formclass.no_incoming_processing = False
    formclass.verbose_name = 'messaging provider'
    formclass.verbose_name_plural = 'messaging providers'

    return backend_list_editor(request,
                               None,
                               formclass,
                               rest,
                               bypass_conference_filter=True,
                               object_queryset=MessagingProvider.objects.filter(series=series),
                               instancemaker=lambda: MessagingProvider(series=series),
                               breadcrumbs=[
                                   ('/events/admin/', 'Series'),
                                   ('/events/admin/_series/{}/'.format(series.id), series.name),
                               ]
    )


###
# Non-simple-editor views
###
def view_registration_ticket(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, pk=regid)

    resp = HttpResponse(content_type='application/pdf')
    try:
        render_jinja_ticket(reg, resp, JINJA_TEMPLATE_ROOT, settings.REGISTER_FONTS)
    except Exception as e:
        return HttpResponse("Exception rendering ticket: {}".format(e.__repr__()), content_type='text/plain')
    return resp


def view_registration_badge(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, pk=regid)

    resp = HttpResponse(content_type='application/pdf')
    try:
        render_jinja_badges(conference, settings.REGISTER_FONTS, [reg.safe_export(), ], resp, False, False)
    except Exception as e:
        print("Exception rendering badge: {}".format(e))
        return HttpResponse("Exception rendering badge: {}".format(e.__repr__()), content_type='text/plain')
    return resp


def view_multi_registration_badge(request, urlname):
    regids = request.GET.get('idlist')
    try:
        ids = [int(i) for i in regids.split(',')]
    except Exception:
        raise Http404("Parameter idlist is not list of integers")

    conference = get_authenticated_conference(request, urlname)
    regs = list(ConferenceRegistration.objects.filter(conference=conference, id__in=ids))
    errs = []
    for r in regs:
        if r.canceledat:
            errs.append('Registration for {} has been canceled'.format(r.fullname))
    if errs:
        if len(errs) > 10:
            messages.warning(request, "Pre-check returned {} errors. Try with a smaller set.".format(len(errs)))
        else:
            for e in errs:
                messages.warning(request, e)
            messages.warning(request, 'No badges have been generated due to previous error(s)')
        return HttpResponseRedirect("../")

    resp = HttpResponse(content_type='application/pdf')
    try:
        render_jinja_badges(conference, settings.REGISTER_FONTS, [r.safe_export() for r in regs], resp, False, False)
    except Exception as e:
        return HttpResponse("Exception rendering badges: {}".format(e.__repr__()), content_type='text/plain')
    return resp


def pendinginvoices(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return render(request, 'confreg/admin_pending_invoices.html', {
        'conference': conference,
        'invoices': OrderedDict((
            ('Attendee invoices', Invoice.objects.filter(paidat__isnull=True, conferenceregistration__conference=conference)),
            ('Multi-registration invoices', Invoice.objects.filter(paidat__isnull=True, bulkpayment__conference=conference)),
            ('Sponsor invoices', Invoice.objects.filter(paidat__isnull=True, sponsor__conference=conference)),
        )),
    })


@transaction.atomic
def pendinginvoices_cancel(request, urlname, invoiceid):
    conference = get_authenticated_conference(request, urlname)
    invoice = get_object_or_404(Invoice, pk=invoiceid, paidat__isnull=True)

    # Have to verify that this invoice is actually for this conference
    if not (
            ConferenceRegistration.objects.filter(conference=conference, invoice=invoice).exists() or
            BulkPayment.objects.filter(conference=conference, invoice=invoice).exists() or
            Sponsor.objects.filter(conference=conference, invoice=invoice).exists()
    ):
        raise PermissionDenied("Invoice not for this conference")

    if request.method == 'POST':
        form = ConferenceInvoiceCancelForm(data=request.POST)
        if form.is_valid():
            manager = InvoiceManager()
            try:
                manager.cancel_invoice(invoice, form.cleaned_data['reason'], request.user.username)
                messages.info(request, 'Invoice {} canceled.'.format(invoice.id))
                return HttpResponseRedirect('../../')
            except Exception as e:
                messages.error(request, 'Failed to cancel invoice: {}'.format(e))
    else:
        form = ConferenceInvoiceCancelForm()

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'whatverb': 'Cancel invoice',
        'savebutton': 'Cancel invoice',
        'cancelname': 'Return without canceling',
        'cancelurl': '../../',
        'note': 'Canceling invoice #{} ({}) will disconnect it from the associated objects and send a notification to the recipient of the invoice ({}).'.format(invoice.id, invoice.title, invoice.recipient_name),
    })


def multiregs(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return render(request, 'confreg/admin_multireg_list.html', {
        'conference': conference,
        'bulkpays': BulkPayment.objects.select_related('user', 'invoice__paidusing').prefetch_related('conferenceregistration_set').filter(conference=conference).order_by('-paidat', '-createdat'),
        'highlight': get_int_or_error(request.GET, 'b', -1),
        'helplink': 'registrations',
    })


@transaction.atomic
def multireg_refund(request, urlname, bulkid):
    conference = get_authenticated_conference(request, urlname)

    bulkpay = get_object_or_404(BulkPayment, pk=bulkid, conference=conference)
    if bulkpay.conferenceregistration_set.exists():
        messages.error(request, "This bulk payment has registrations, cannot be canceled!")
        return HttpResponseRedirect("../../")

    invoice = bulkpay.invoice
    if not invoice:
        messages.error(request, "This bulk payment does not have an invoice!")
        return HttpResponseRedirect("../../")
    if not invoice.paidat:
        messages.error(request, "This bulk payment invoice has not been paid!")
        return HttpResponseRedirect("../../")

    if request.method == 'POST':
        form = BulkPaymentRefundForm(invoice, data=request.POST)
        if form.is_valid():
            manager = InvoiceManager()
            manager.refund_invoice(invoice, 'Multi registration refunded', form.cleaned_data['amount'], form.cleaned_data['vatamount'], conference.vat_registrations)

            send_conference_notification(
                conference,
                'Multi registration {} refunded'.format(bulkpay.id),
                'Multi registration {} purchased by {} {} has been refunded.\nNo registrations were active in this multi registration, and the multi registration has now been deleted.\n'.format(bulkpay.id, bulkpay.user.first_name, bulkpay.user.last_name),
            )
            bulkpay.delete()

            messages.info(request, 'Multi registration has been refunded and deleted.')
            return HttpResponseRedirect("../../")
    else:
        form = BulkPaymentRefundForm(invoice, initial={'amount': invoice.total_amount - invoice.total_vat, 'vatamount': invoice.total_vat})

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'whatverb': 'Refund',
        'what': 'multi registration',
        'savebutton': 'Refund',
        'cancelurl': '../../',
        'breadcrumbs': [('/events/admin/{}/multiregs/'.format(conference.urlname), 'Multi Registrations'), ],
        'helplink': 'registrations',
    })


def addoptorders(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return render(request, 'confreg/admin_addoptorder_list.html', {
        'conference': conference,
        'orders': PendingAdditionalOrder.objects.select_related('reg', 'invoice__paidusing').filter(reg__conference=conference).order_by('-payconfirmedat', '-createtime'),
        'helplink': 'registrations#options',
    })


def paymentstats(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    innersql = """WITH t AS (
  SELECT
    r.id,
    coalesce(
      r.invoice_id,
      CASE WHEN v.vouchervalue IS NOT NULL THEN NULL ELSE bp.invoice_id END,
      pv.invoice_id
    ) AS invoiceid,
    vouchervalue,
    pv.batch_id IS NOT NULL AS purchasedvoucher
  FROM confreg_conferenceregistration r
  LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
  LEFT JOIN confreg_prepaidvoucher v ON (v.vouchervalue=r.vouchercode and v.conference_id=r.conference_id)
  LEFT JOIN confsponsor_purchasedvoucher pv ON pv.batch_id=v.batch_id
  WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND canceledat IS NULL
)"""

    regs_per_method = exec_to_list("""{}
,t2 AS (
  SELECT
    CASE WHEN t.invoiceid IS NULL AND vouchervalue IS NULL THEN 'Not paid' WHEN t.invoiceid IS NULL THEN 'Given voucher' ELSE pm.internaldescription END AS method
  FROM t
  LEFT JOIN (invoices_invoice i INNER JOIN invoices_invoicepaymentmethod pm ON pm.id=i.paidusing_id) ON i.id=t.invoiceid
)
SELECT method AS "Payment method", count(*) AS "Number of registrations"
FROM t2
GROUP BY ROLLUP(method)
ORDER BY GROUPING(method), 2 DESC
""".format(innersql), {
        'confid': conference.id,
    })

    invoices_per_method = exec_to_list("""{}
SELECT pm.internaldescription, count(*) AS "Number of invoices", avg(total_amount)::numeric(10,2) AS "Average invoice amount", sum(total_amount) AS "Total invoice amount"
FROM invoices_invoice i
INNER JOIN invoices_invoicepaymentmethod pm ON i.paidusing_id=pm.id
WHERE i.id IN (SELECT invoiceid FROM t)
GROUP BY ROLLUP(pm.internaldescription)
ORDER BY GROUPING(pm.internaldescription), 2 DESC""".format(innersql), {
        'confid': conference.id,
    })

    sponsors_per_method = exec_to_list("""
WITH t AS (
  SELECT l.levelname, l.levelcost, grouping(pm.internaldescription) as istotal, pm.internaldescription, count(*) AS num
  FROM confsponsor_sponsor s
  INNER JOIN confsponsor_sponsorshiplevel l ON s.level_id=l.id
  INNER JOIN invoices_invoice i ON s.invoice_id=i.id
  INNER JOIN invoices_invoicepaymentmethod pm ON pm.id=i.paidusing_id
  WHERE confirmed AND s.conference_id=%(confid)s
  GROUP BY l.levelcost, l.levelname, ROLLUP(pm.internaldescription)
)
SELECT
  CASE WHEN row_number() OVER (PARTITION BY levelname ORDER BY istotal, num DESC) = 1 THEN levelname ELSE NULL END,
  internaldescription,
  num
FROM t
ORDER BY levelcost desc, istotal, num desc""", {
        'confid': conference.id,
    })

    return render(request, 'confreg/admin_payment_stats.html', {
        'conference': conference,
        'tables': [
            {
                'title': 'Registrations per payment method',
                'columns': ['Payment method', 'Number of registrations'],
                'extraclasses': 'lastrowbold',
                'rows': [(r, None) for r in regs_per_method],
            },
            {
                'title': 'Invoices per payment method',
                'columns': ['Payment method', 'Number of invoices', 'Average invoice amount', 'Total invoice amount'],
                'extraclasses': 'lastrowbold',
                'rows': [(r, None) for r in invoices_per_method],
            },
            {
                'title': 'Sponsors per payment method and level',
                'columns': ['Level', 'Payment method', 'Number of sponsors'],
                'rows': [(r, None) for r in sponsors_per_method],
            },
        ],
        'regs_per_method': regs_per_method,
        'invoices_per_method': invoices_per_method,
    })


def prepaidorders(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return render(request, 'confreg/admin_prepaidorders_list.html', {
        'conference': conference,
        'orders': PurchasedVoucher.objects.select_related('sponsor', 'user', 'invoice', 'batch').filter(conference=conference).annotate(num_used=Count('batch__prepaidvoucher__user')).order_by('-invoice__paidat', '-invoice__id'),
        'helplink': 'vouchers',
    })


@transaction.atomic
def prepaidorder_refund(request, urlname, orderid):
    conference = get_authenticated_conference(request, urlname)

    order = get_object_or_404(PurchasedVoucher, pk=orderid, conference=conference)

    if PrepaidBatch.objects.filter(pk=order.batch_id).aggregate(used=Count('prepaidvoucher__user'))['used'] > 0:
        # This link should not exist in the first place, but double check if someone
        # used the voucher in between the click.
        messages.error(request, 'Cannot refund order, there are used vouchers in the batch!')
        return HttpResponseRedirect("../../")

    invoice = order.invoice
    if not invoice:
        messages.error(request, 'Order does not have an invoice, there is nothing to refund!')
        return HttpResponseRedirect("../../")
    if not invoice.paidat:
        messages.error(request, 'Invoice for this order has not been paid, there is nothing to refund!')
        return HttpResponseRedirect("../../")

    if request.method == 'POST':
        form = PurchasedVoucherRefundForm(data=request.POST)
        if form.is_valid():
            # Actually issue the refund
            manager = InvoiceManager()
            manager.refund_invoice(invoice, 'Prepaid order refunded', invoice.total_amount - invoice.total_vat, invoice.total_vat, conference.vat_registrations)

            send_conference_notification(
                conference,
                'Prepaid order {} refunded'.format(order.id),
                'Prepaid order {} purchased by {} {} has been refunded.\nNo vouchers were in use, and the order and batch have both been deleted.\n'.format(order.id, order.user.first_name, order.user.last_name),
            )
            order.batch.delete()
            order.delete()

            messages.info(request, 'Order has been refunded and deleted.')
            return HttpResponseRedirect("../../")
    else:
        form = PurchasedVoucherRefundForm()

    if invoice.total_vat > 0:
        note = 'You are about to refund {}{} ({}{} + {}{} VAT) for invoice {}. Please confirm that this is what you want!'.format(settings.CURRENCY_SYMBOL, invoice.total_amount, settings.CURRENCY_SYMBOL, invoice.total_amount - invoice.total_vat, settings.CURRENCY_SYMBOL, invoice.total_vat, invoice.id)
    else:
        note = 'You are about to refund {}{} for invoice {}. Please confirm that this is what you want!'.format(settings.CURRENCY_SYMBOL, invoice.total_amount, invoice.id)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'note': note,
        'whatverb': 'Refund',
        'what': 'repaid vouchers',
        'savebutton': 'Refund',
        'cancelurl': '../../',
        'breadcrumbs': [('/events/admin/{}/prepaidorders/'.format(conference.urlname), 'Prepaid Voucher Orders'), ],
        'helplink': 'vouchers',
    })


@transaction.atomic
def purge_personal_data(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    if conference.personal_data_purged:
        messages.warning(request, 'Personal data for this conference has already been purged')
        return HttpResponseRedirect('../')

    if request.method == 'POST':
        exec_no_result("INSERT INTO confreg_aggregatedtshirtsizes (conference_id, size_id, num) SELECT conference_id, shirtsize_id, count(*) FROM confreg_conferenceregistration WHERE conference_id=%(confid)s AND shirtsize_id IS NOT NULL GROUP BY conference_id, shirtsize_id", {'confid': conference.id, })
        exec_no_result("INSERT INTO confreg_aggregateddietary (conference_id, dietary, num) SELECT conference_id, lower(dietary), count(*) FROM confreg_conferenceregistration WHERE conference_id=%(confid)s AND dietary IS NOT NULL AND dietary != '' GROUP BY conference_id, lower(dietary)", {'confid': conference.id, })
        exec_no_result("INSERT INTO confreg_aggregatepronouns (conference_id, pronouns, num) SELECT conference_id, pronouns, count(*) FROM confreg_conferenceregistration WHERE conference_id=%(confid)s GROUP BY conference_id, pronouns", {'confid': conference.id, })
        exec_no_result("UPDATE confreg_conferenceregistration SET shirtsize_id=NULL, dietary='', phone='', address='', pronouns=0 WHERE conference_id=%(confid)s", {'confid': conference.id, })
        conference.personal_data_purged = timezone.now()
        conference.save()
        messages.info(request, "Personal data purged from conference")
        return HttpResponseRedirect('../')

    return render(request, 'confreg/admin_purge_personal_data.html', {
        'conference': conference,
        'helplink': 'personaldata',
        'counts': exec_to_dict("""SELECT
  count(1) FILTER (WHERE shirtsize_id IS NOT NULL) AS "T-shirt size registrations",
  count(1) FILTER (WHERE dietary IS NOT NULL AND dietary != '') AS "Dietary needs",
  count(1) FILTER (WHERE phone IS NOT NULL AND phone != '') AS "Phone numbers",
  count(1) FILTER (WHERE address IS NOT NULL AND address != '') AS "Addresses",
  count(1) FILTER (WHERE pronouns != 0) AS "Pronouns"
FROM confreg_conferenceregistration WHERE conference_id=%(confid)s""", {
            'confid': conference.id,
        })[0],
    })


def tweetcampaignselect(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    if request.method == 'POST':
        form = TweetCampaignSelectForm(data=request.POST)
        if form.is_valid():
            return HttpResponseRedirect("{}/".format(form.cleaned_data['campaigntype']))
    else:
        form = TweetCampaignSelectForm()

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'whatverb': 'Create campaign',
        'savebutton': 'Select campaign type',
        'cancelurl': '../../',
        'helplink': 'integrations#campaigns',
    })


def tweetcampaign(request, urlname, typeid):
    conference = get_authenticated_conference(request, urlname)

    campaign = get_campaign_from_id(typeid)

    if request.method == 'GET' and 'fieldpreview' in request.GET:
        try:
            return campaign.get_dynamic_preview(conference, request.GET['fieldpreview'], request.GET['previewval'])
        except Exception as e:
            return HttpResponse('Exception rendering preview: {}'.format(e), content_type='text/plain', status=400)

    if request.method == 'POST':
        form = campaign.form(conference, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.generate_tweets(request.user)
                messages.info(request, "Campaign tweets generated")
                return HttpResponseRedirect("../../queue/")
            except Exception as e:
                form.add_error('content_template', 'Exception generating tweets: {}'.format(e))
    else:
        form = campaign.form(conference)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'whatverb': 'Create campaign',
        'savebutton': "Create campaign",
        'cancelurl': '../../../',
        'note': campaign.note,
        'helplink': 'integrations#campaigns',
    })


def manage_series(request, seriesid):
    series = get_authenticated_series(request, seriesid)

    return render(request, 'confreg/admin_dashboard_series.html', {
        'series': series,
        'breadcrumbs': (('/events/admin/', 'Series'),),
    })


class DelimitedWriter(object):
    def __init__(self, delimiter):
        self.delimiter = delimiter
        self.response = HttpResponse(content_type='text/plain; charset=utf-8')
        self.writer = csv.writer(self.response, delimiter=delimiter)

    def writeloaded(self):
        self.writer.writerow(["File loaded", timezone.now()])

    def columns(self, columns, grouping=False):
        self.writer.writerow(columns)

    def write_query(self, query, params):
        self.write_rows(exec_to_list(query, params))

    def write_rows(self, rows, grouping=False):
        for r in rows:
            self.writer.writerow(r)

    def is_structured(self):
        return False


class JsonWriter(object):
    def __init__(self):
        self.d = {}

    def writeloaded(self):
        self.d['FileLoaded'] = timezone.now()

    def columns(self, columns, grouping=False):
        self.grouping = grouping
        if grouping:
            self.columns = columns[1:]
        else:
            self.columns = columns

    def write_query(self, query, params):
        self.write_rows(exec_to_list(query, params))

    def write_rows(self, rows):
        if self.grouping:
            data = {}
        else:
            data = []
        for r in rows:
            if self.grouping:
                data[r[0]] = dict(list(zip(self.columns, r[1:])))
            else:
                data.append(dict(list(zip(self.columns, r))))
        self.d['data'] = data

    def is_structured(self):
        return True

    @property
    def response(self):
        r = HttpResponse(json.dumps(self.d, cls=DjangoJSONEncoder), content_type='application/json')
        r['Access-Control-Allow-Origin'] = '*'
        return r


class YamlWriter(JsonWriter):
    def __init__(self):
        super().__init__()

    @property
    def response(self):
        import yaml
        r = HttpResponse(yaml.dump(self.d), content_type='application/yaml')
        r['Access-Control-Allow-Origin'] = '*'
        return r


def _structured_tokendata(tokendata, dataformat):
    if dataformat == 'json':
        return HttpResponse(json.dumps(tokendata,
                                       cls=JsonSerializer,
                                       indent=2),
                            content_type='application/json')
    elif dataformat == 'yaml':
        import yaml
        return HttpResponse(yaml.dump(tokendata),
                            content_type='application/yaml')
    raise Http404()


def tokendata(request, urlname, token, datatype, dataformat, subrequest=None):
    conference = get_conference_or_404(urlname)
    if not AccessToken.objects.filter(conference=conference, token=token, permissions__contains=[datatype, ]).exists():
        raise Http404()

    if subrequest is not None and datatype not in ('sponsorclaims'):
        raise Http404()  # Only sponsorclaims have subrequests for now:

    if dataformat.lower() == 'csv':
        writer = DelimitedWriter(delimiter=",")
    elif dataformat.lower() == 'tsv':
        writer = DelimitedWriter(delimiter="\t")
    elif dataformat.lower() == 'json':
        writer = JsonWriter()
    elif dataformat.lower() == 'yaml':
        if not has_yaml:
            raise Http404("YAML not supported on this server")
        writer = YamlWriter()
    else:
        raise Http404()

    writer.writeloaded()

    if datatype == 'regtypes':
        writer.columns(['Type', 'Confirmed', 'Unconfirmed', 'Canceled'], True)
        writer.write_query("SELECT regtype, count(payconfirmedat) - count(canceledat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed, count(canceledat) AS cancled FROM confreg_conferenceregistration r RIGHT JOIN confreg_registrationtype rt ON rt.id=r.regtype_id WHERE rt.conference_id=%(confid)s GROUP BY rt.id ORDER BY rt.sortkey", {'confid': conference.id, })
    elif datatype == 'discounts' or datatype == 'discountspublic':
        writer.columns(['Code', 'Max uses', 'Confirmed', 'Unconfirmed'], True)
        if datatype == 'discounts':
            extrawhere = ''
        else:
            extrawhere = 'AND public'
        writer.write_query("SELECT code, maxuses, count(payconfirmedat) - count(canceledat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed FROM confreg_conferenceregistration r RIGHT JOIN confreg_discountcode dc ON dc.code=r.vouchercode WHERE dc.conference_id=%(confid)s AND (r.conference_id=%(confid)s OR r.conference_id IS NULL) {0} GROUP BY dc.id ORDER BY code".format(extrawhere), {'confid': conference.id, })
    elif datatype == 'vouchers':
        writer.columns(["Buyer", "Used", "Unused", "Purchased"])
        writer.write_query("SELECT b.buyername, count(v.user_id) AS used, count(*) FILTER (WHERE v.user_id IS NULL) AS unused,  EXISTS (SELECT 1 FROM confsponsor_purchasedvoucher pv WHERE pv.batch_id=b.id)::int AS purchased FROM confreg_prepaidbatch b INNER JOIN confreg_prepaidvoucher v ON v.batch_id=b.id WHERE b.conference_id=%(confid)s GROUP BY b.id ORDER BY buyername", {'confid': conference.id, })
    elif datatype == 'sponsors':
        (headers, data) = get_sponsor_dashboard_data(conference)
        writer.columns(headers, True)
        writer.write_rows(data)
    elif datatype == 'addopts':
        writer.columns(['sysid', 'Option', 'Confirmed', 'Unconfirmed', 'Remaining'])
        writer.write_query("""WITH direct AS (
 SELECT
  ao.id,
  ao.name,
  count(payconfirmedat) AS confirmed,
  count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed,
  ao.maxcount
 FROM confreg_conferenceadditionaloption ao
 LEFT JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceadditionaloption_id=ao.id
 LEFT JOIN confreg_conferenceregistration r ON r.id=rao.conferenceregistration_id
 WHERE ao.conference_id=%(confid)s
 GROUP BY ao.id
), pending AS (
 SELECT
  paoo.conferenceadditionaloption_id AS id,
  count(*) AS unconfirmed
 FROM confreg_pendingadditionalorder pao
 INNER JOIN confreg_pendingadditionalorder_options paoo ON paoo.pendingadditionalorder_id=pao.id
 INNER JOIN confreg_conferenceregistration r ON r.id=pao.reg_id
 WHERE pao.payconfirmedat IS NULL AND r.conference_id=%(confid)s
 GROUP BY paoo.conferenceadditionaloption_id
)
SELECT direct.id, direct.name,
       direct.confirmed,
       direct.unconfirmed+COALESCE(pending.unconfirmed, 0),
       CASE WHEN maxcount > 0 THEN maxcount ELSE NULL END-(direct.confirmed+direct.unconfirmed+COALESCE(pending.unconfirmed, 0))
FROM direct
LEFT JOIN pending ON direct.id=pending.id
ORDER BY name""", {'confid': conference.id})
    elif datatype == 'schedule':
        return _structured_tokendata(_scheduledata(request, conference), dataformat)
    elif datatype == 'sponsorlevels':
        return _structured_tokendata(sponsorleveldata(conference), dataformat)
    elif datatype == 'sponsorclaims':
        if subrequest is not None:
            return sponsorclaimsfile(conference, subrequest.lstrip('/'))
        else:
            return _structured_tokendata(sponsorclaimsdata(conference), dataformat)
    elif datatype == 'sessions':
        sessiondata(conference, writer)
    else:
        raise Http404()

    return writer.response


def csvembed(iter):
    f = io.StringIO()
    writer = csv.writer(f, lineterminator='', delimiter=';')
    writer.writerow(iter)
    return f.getvalue()


def sessiondata(conference, writer):
    result = []
    status_filter = []
    sessions = ConferenceSession.objects.filter(conference=conference)
    header = ['id', 'title', 'shorttitle', 'abstract', 'status',
              'track', 'starttime', 'endtime', 'recordingconsent', 'room', 'submissionnote']
    if writer.is_structured():
        header.append('speakers')
    else:
        header.append('speaker')
        header.append('company')
        header.append('email')
    writer.columns(header)
    writer.grouping = False
    for s in sessions:
        row = [
            s.id,
            s.title,
            s.shorttitle,
            s.abstract,
            s.status_string,
            None if s.track is None else s.track.trackname,
            s.starttime,
            s.endtime,
            s.recordingconsent,
            None if s.room is None else s.room.roomname,
            s.submissionnote,
        ]
        if writer.is_structured():
            speakers = []
            for spk in s.speaker.all():
                speakers.append({
                    'name': spk.name,
                    'email': spk.email,
                    'company': spk.company
                })
            row.append(speakers)
        else:
            speaker_names = csvembed(map(lambda spk: spk.name, s.speaker.all()))
            speaker_emails = csvembed(map(lambda spk: spk.email, s.speaker.all()))
            speaker_companies = csvembed(map(lambda spk: spk.company, s.speaker.all()))
            row.append(speaker_names)
            row.append(speaker_emails)
            row.append(speaker_companies)
        result.append(row)
    writer.write_rows(result)


def registration_dashboard_send_email(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return attendee_email_form(request,
                               conference,
                               BaseAttendeeEmailProvider,
                               breadcrumbs=[('../', 'Registration list'), ],
                               )


def conference_session_send_email(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    class ConferenceSessionAttendeeEmailProvider(AttendeeEmailQuerySampleMixin, BaseAttendeeEmailProvider):
        @property
        def query(self):
            return """
SELECT r.id AS regid, s.user_id, s.fullname, COALESCE(r.email, u.email) AS email
FROM confreg_speaker s
INNER JOIN auth_user u ON u.id=s.user_id
LEFT JOIN confreg_conferenceregistration r ON (r.conference_id=%(conference)s AND r.attendee_id=s.user_id)
WHERE EXISTS (
 SELECT 1 FROM confreg_conferencesession sess
 INNER JOIN confreg_conferencesession_speaker ccs ON sess.id=ccs.conferencesession_id
 WHERE conferencesession_id=ANY(%(idlist)s) AND sess.conference_id=%(conference)s
 AND speaker_id=s.id)"""

        @property
        def allow_attendee_ref(self):
            if not self.get_recipients():
                # If there are no recipients, we allow it
                return True
            return not exec_to_scalar("SELECT EXISTS (SELECT 1 FROM ({}) WHERE regid IS NULL)".format(self.query), self.queryparams)

    return attendee_email_form(request,
                               conference,
                               ConferenceSessionAttendeeEmailProvider,
                               [('../', 'Conference sessions'), ],
                               )


@transaction.atomic
def registration_dashboard_send_dm(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, pk=regid)

    if not reg.messaging:
        # Should never have the link, but just in case
        messages.warning(request, 'This registration has no direct messaging configured')
        return HttpResponseRedirect("../")

    maxlength = get_messaging_class(reg.messaging.provider.classname).direct_message_max_length
    if request.method == 'POST':
        form = BackendRegistrationDmForm(maxlength, data=request.POST)
        if form.is_valid():
            send_reg_direct_message(reg, form.cleaned_data['message'])
            messages.info(request, "Direct message sent.")
            return HttpResponseRedirect("../")
    else:
        form = BackendRegistrationDmForm(maxlength)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'what': 'new direct message',
        'savebutton': 'Send direct message',
        'cancelurl': '../',
        'breadcrumbs': [('../../', 'Registration list'), ('../', reg.fullname)],
    })


@superuser_required
@transaction.atomic
def merge_speakers(request, speakerid):
    oldspeaker = get_object_or_404(Speaker, id=speakerid)

    if request.method == 'POST':
        form = BackendMergeSpeakerForm(oldspeaker, data=request.POST)
        if form.is_valid():
            newspeaker = form.cleaned_data['targetspeaker']

            oldprofiletxt = "{} ({} - {})".format(oldspeaker.fullname, oldspeaker.user, oldspeaker.user.email if oldspeaker.user else '* no user/email*')
            newprofiletxt = "{} ({} - {})".format(newspeaker.fullname, newspeaker.user, newspeaker.user.email if newspeaker.user else '* no user/email*')

            sessions = list(oldspeaker.conferencesession_set.all())
            for sess in sessions:
                sess.speaker.add(newspeaker)

            oldspeaker.delete()

            messages.info(request, "Profile {} merged into {}, and {} has been deleted. {} sessions transferred.".format(
                oldprofiletxt,
                newprofiletxt,
                oldprofiletxt,
                len(sessions)
            ))
            return HttpResponseRedirect("../../{}/".format(newspeaker.id))
    else:
        form = BackendMergeSpeakerForm(oldspeaker)

    return render(request, 'confreg/admin_backend_form.html', {
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'whatverb': 'Merge',
        'what': 'speaker profiles',
        'savebutton': 'Merge into speaker profile, deleting the source profile',
        'cancelurl': '../',
    })


def cancelrequests(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    patterns = RefundPattern.objects.filter(conference=conference).filter(Q(fromdate__isnull=False) | Q(todate__isnull=False)).order_by('fromdate')
    requested = list(ConferenceRegistration.objects.select_related('regtype').filter(conference=conference, cancelrequestedat__isnull=False).order_by('canceledat', 'cancelrequestedat'))

    for r in requested:
        if r.regtype.cost == 0:
            r.refund_pattern_reason = 'Free registration'
        elif r.prepaidvoucher_set.exists():
            r.refund_pattern_reason = 'Made using voucher'
        else:
            matches = []
            for p in patterns:
                if p.matches_date(r.cancelrequestedat.date()):
                    matches.append(p)

            r.matched_refund_rules = matches

    return render(request, 'confreg/admin_cancel_requests.html', {
        'conference': conference,
        'requested': requested,
        'helplink': 'registrations#cancel',
    })
