from django.shortcuts import render, get_object_or_404
from django.utils.html import escape
from django.db import transaction, connection
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

import csv
import json
from collections import OrderedDict

from postgresqleu.util.db import exec_to_list, exec_to_dict, exec_no_result, exec_to_scalar
from postgresqleu.util.decorators import superuser_required
from postgresqleu.util.messaging.twitter import Twitter, TwitterSetup
from postgresqleu.util.messaging import messaging_implementations, get_messaging_class
from postgresqleu.util.messaging.util import send_reg_direct_message
from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.confreg.util import get_authenticated_conference, get_authenticated_series
from postgresqleu.util.request import get_int_or_error

from .jinjafunc import JINJA_TEMPLATE_ROOT
from .jinjapdf import render_jinja_ticket, render_jinja_badges
from .util import send_conference_mail, get_conference_or_404, send_conference_notification

from .models import Conference, ConferenceSeries
from .models import ConferenceRegistration, Speaker
from .models import PrepaidBatch
from .models import BulkPayment
from .models import AccessToken
from .models import ShirtSize
from .models import PendingAdditionalOrder
from .models import ConferenceTweetQueue
from .models import MessagingProvider

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.confsponsor.util import get_sponsor_dashboard_data
from postgresqleu.confsponsor.models import PurchasedVoucher, Sponsor

from .backendforms import BackendConferenceForm, BackendSuperConferenceForm, BackendRegistrationForm
from .backendforms import BackendRegistrationTypeForm, BackendRegistrationClassForm
from .backendforms import BackendRegistrationDayForm, BackendAdditionalOptionForm
from .backendforms import BackendTrackForm, BackendRoomForm, BackendConferenceSessionForm
from .backendforms import BackendSpeakerForm, BackendTagForm
from .backendforms import BackendConferenceSessionSlotForm, BackendVolunteerSlotForm
from .backendforms import BackendFeedbackQuestionForm, BackendDiscountCodeForm
from .backendforms import BackendAccessTokenForm
from .backendforms import BackendConferenceSeriesForm
from .backendforms import BackendTshirtSizeForm
from .backendforms import BackendNewsForm
from .backendforms import BackendTweetQueueForm, BackendHashtagForm
from .backendforms import TweetCampaignSelectForm
from .backendforms import BackendSendEmailForm
from .backendforms import BackendRefundPatternForm
from .backendforms import ConferenceInvoiceCancelForm
from .backendforms import PurchasedVoucherRefundForm
from .backendforms import BulkPaymentRefundForm
from .backendforms import BackendMessagingForm
from .backendforms import BackendSeriesMessagingForm
from .backendforms import BackendRegistrationDmForm

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
    return backend_process_form(request,
                                urlname,
                                BackendRegistrationForm,
                                regid,
                                allow_new=False,
                                breadcrumbs=(
                                    ('/events/admin/{}/regdashboard/'.format(urlname), 'Registration dashboard'),
                                    ('/events/admin/{}/regdashboard/list/'.format(urlname), 'Registration list'),
                                    ('/events/admin/{}/regdashboard/list/{}/'.format(urlname, regid), 'Registration'),
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
                               BackendSpeakerForm,
                               rest,
                               allow_new=False,
                               allow_delete=False,
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
                               instancemaker=lambda: ConferenceTweetQueue(conference=conference, author=request.user)
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
            """INSERT INTO confreg_conferencemessaging (conference_id, provider_id, broadcast, privatebcast, notification, orgnotification, config)
SELECT %(confid)s, id, false, false, false, false, '{}'
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
    render_jinja_ticket(reg, resp, systemroot=JINJA_TEMPLATE_ROOT)
    return resp


def view_registration_badge(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, pk=regid)

    resp = HttpResponse(content_type='application/pdf')
    render_jinja_badges(conference, [reg.safe_export(), ], resp, False, False)
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
        return HttpResonseRedirect("../../")
    if not invoice.paidat:
        messages.error(request, "This bulk payment invoice has not been paid!")
        return HttpResonseRedirect("../../")

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

    if settings.EU_VAT:
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
        exec_no_result("UPDATE confreg_conferenceregistration SET shirtsize_id=NULL, dietary='', phone='', address='' WHERE conference_id=%(confid)s", {'confid': conference.id, })
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
  count(1) FILTER (WHERE address IS NOT NULL AND address != '') AS "Addresses"
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
            return HttpResponse('Exception rendering preview: {}'.format(e), content_type='text/plain', status=500)

    if request.method == 'POST':
        form = campaign.form(conference, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.generate_tweets(request.user)
                messages.info(request, "Campaign tweets generated")
                return HttpResponseRedirect("../../queue/")
            except Exception as e:
                form.add_error('content_template', 'Exception rendering template: {}'.format(e))
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

    @property
    def response(self):
        r = HttpResponse(json.dumps(self.d, cls=DjangoJSONEncoder), content_type='application/json')
        r['Access-Control-Allow-Origin'] = '*'
        return r


def tokendata(request, urlname, token, datatype, dataformat):
    conference = get_conference_or_404(urlname)
    if not AccessToken.objects.filter(conference=conference, token=token, permissions__contains=[datatype, ]).exists():
        raise Http404()

    if dataformat.lower() == 'csv':
        writer = DelimitedWriter(delimiter=",")
    elif dataformat.lower() == 'tsv':
        writer = DelimitedWriter(delimiter="\t")
    elif dataformat.lower() == 'json':
        writer = JsonWriter()
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
    else:
        raise Http404()

    return writer.response


def _attendee_email_form(request, conference, query, breadcrumbs):
    if request.method == 'POST':
        idlist = list(map(int, request.POST['idlist'].split(',')))
    else:
        if 'idlist' not in request.GET:
            raise Http404("Mandatory parameter idlist is missing")
        idlist = list(map(int, request.GET['idlist'].split(',')))

    queryparams = {'conference': conference.id, 'idlist': idlist}
    recipients = exec_to_dict(query, queryparams)

    initial = {
        '_from': '{0} <{1}>'.format(conference.conferencename, conference.contactaddr),
        'recipients': escape(", ".join(['{0} <{1}>'.format(x['fullname'], x['email']) for x in recipients])),
        'idlist': ",".join(map(str, idlist)),
        'storeonregpage': True,
    }

    if request.method == 'POST':
        p = request.POST.copy()
        p['recipients'] = initial['recipients']
        form = BackendSendEmailForm(conference, data=p, initial=initial)
        if form.is_valid():
            with transaction.atomic():
                if form.cleaned_data['storeonregpage']:
                    mailid = exec_to_scalar("INSERT INTO confreg_attendeemail (conference_id, sentat, subject, message, tocheckin, tovolunteers) VALUES (%(confid)s, CURRENT_TIMESTAMP, %(subject)s, %(message)s, false, false) RETURNING id", {
                        'confid': conference.id,
                        'subject': form.cleaned_data['subject'],
                        'message': form.cleaned_data['message'],
                    })
                for r in recipients:
                    send_conference_mail(conference,
                                         r['email'],
                                         form.cleaned_data['subject'],
                                         'confreg/mail/attendee_mail.txt',
                                         {
                                             'body': form.cleaned_data['message'],
                                             'linkback': form.cleaned_data['storeonregpage'],
                                         },
                                         receivername=r['fullname'],
                    )

                    if form.cleaned_data['storeonregpage']:
                        if r['regid']:
                            # Existing registration, so attach directly to attendee
                            exec_no_result("INSERT INTO confreg_attendeemail_registrations (attendeemail_id, conferenceregistration_id) VALUES (%(mailid)s, %(reg)s)", {
                                'mailid': mailid,
                                'reg': r['regid'],
                            })
                        else:
                            # No existing registration, so queue it up in case the attendee
                            # might register later. We have the userid...
                            exec_no_result("INSERT INTO confreg_attendeemail_pending_regs (attendeemail_id, user_id) VALUES (%(mailid)s, %(userid)s)", {
                                'mailid': mailid,
                                'userid': r['user_id'],
                            })
                if form.cleaned_data['storeonregpage']:
                    messages.info(request, "Email sent to %s attendees, and added to their registration pages when possible" % len(recipients))
                else:
                    messages.info(request, "Email sent to %s attendees" % len(recipients))

            return HttpResponseRedirect('../')
    else:
        form = BackendSendEmailForm(conference, initial=initial)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'what': 'new email',
        'savebutton': 'Send email',
        'cancelurl': '../',
        'breadcrumbs': breadcrumbs,
    })


def registration_dashboard_send_email(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return _attendee_email_form(request,
                                conference,
                                "SELECT id AS regid, attendee_id AS user_id, firstname || ' ' || lastname AS fullname, email FROM confreg_conferenceregistration WHERE conference_id=%(conference)s AND id=ANY(%(idlist)s)",
                                [('../', 'Registration list'), ],
                                )


def conference_session_send_email(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return _attendee_email_form(request,
                                conference,
                                """
SELECT r.id AS regid, s.user_id, s.fullname, COALESCE(r.email, u.email) AS email
FROM confreg_speaker s
INNER JOIN auth_user u ON u.id=s.user_id
LEFT JOIN confreg_conferenceregistration r ON (r.conference_id=%(conference)s AND r.attendee_id=s.user_id)
WHERE EXISTS (
 SELECT 1 FROM confreg_conferencesession sess
 INNER JOIN confreg_conferencesession_speaker ccs ON sess.id=ccs.conferencesession_id
 WHERE conferencesession_id=ANY(%(idlist)s) AND sess.conference_id=%(conference)s
 AND speaker_id=s.id)""",
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
