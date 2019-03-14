from django.shortcuts import render, get_object_or_404
from django.utils.html import escape
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib import messages
from django.conf import settings

import datetime
import csv
import json

from postgresqleu.util.db import exec_to_list, exec_to_dict, exec_no_result, exec_to_scalar
from postgresqleu.util.decorators import superuser_required
from postgresqleu.util.messaging.twitter import Twitter, TwitterSetup
from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.confreg.util import get_authenticated_conference
from postgresqleu.mailqueue.util import send_mail, send_simple_mail

from .jinjafunc import JINJA_TEMPLATE_ROOT
from .jinjapdf import render_jinja_ticket

from .models import Conference, ConferenceSeries
from .models import ConferenceRegistration, Speaker
from .models import AccessToken
from .models import ShirtSize

from postgresqleu.invoices.models import Invoice
from postgresqleu.confsponsor.util import get_sponsor_dashboard_data

from .backendforms import BackendConferenceForm, BackendSuperConferenceForm, BackendRegistrationForm
from .backendforms import BackendRegistrationTypeForm, BackendRegistrationClassForm
from .backendforms import BackendRegistrationDayForm, BackendAdditionalOptionForm
from .backendforms import BackendTrackForm, BackendRoomForm, BackendConferenceSessionForm
from .backendforms import BackendConferenceSessionSlotForm, BackendVolunteerSlotForm
from .backendforms import BackendFeedbackQuestionForm, BackendDiscountCodeForm
from .backendforms import BackendAccessTokenForm
from .backendforms import BackendConferenceSeriesForm
from .backendforms import BackendTshirtSizeForm
from .backendforms import BackendNewsForm
from .backendforms import TwitterForm, TwitterTestForm
from .backendforms import BackendSendEmailForm
from .backendforms import BackendRefundPatternForm


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

    return backend_process_form(request,
                                urlname,
                                BackendSuperConferenceForm,
                                get_object_or_404(Conference, urlname=urlname).pk,
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


def edit_sessions(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendConferenceSessionForm,
                               rest)


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


###
# Non-simple-editor views
###
def view_registration_ticket(request, urlname, regid):
    conference = get_authenticated_conference(request, urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, pk=regid)

    resp = HttpResponse(content_type='application/pdf')
    render_jinja_ticket(reg, resp, systemroot=JINJA_TEMPLATE_ROOT)
    return resp


def pendinginvoices(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    return render(request, 'confreg/admin_pending_invoices.html', {
        'conference': conference,
        'invoices': {
            'Attendee invoices': Invoice.objects.filter(paidat__isnull=True, conferenceregistration__conference=conference),
            'Multi-registration invoices': Invoice.objects.filter(paidat__isnull=True, bulkpayment__conference=conference),
            'Sponsor invoices': Invoice.objects.filter(paidat__isnull=True, sponsor__conference=conference),
        },
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
        conference.personal_data_purged = datetime.datetime.now()
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


@transaction.atomic
def twitter_integration(request, urlname):
    conference = get_authenticated_conference(request, urlname)

    if request.method == 'POST':
        if request.POST.get('activate_twitter', '') == '1':
            # Fetch the oauth codes and re-render the form
            try:
                (auth_url, ownerkey, ownersecret) = TwitterSetup.get_authorization_data()
                request.session['ownerkey'] = ownerkey
                request.session['ownersecret'] = ownersecret
            except Exception as e:
                messages.error(request, 'Failed to talk to twitter: %s' % e)
                return HttpResponseRedirect('.')

            return render(request, 'confreg/admin_integ_twitter.html', {
                'conference': conference,
                'twitter_token_url': auth_url,
                'helplink': 'integrations#twitter',
            })
        elif request.POST.get('pincode', ''):
            if not ('ownerkey' in request.session and 'ownersecret' in request.session):
                messages.error(request, 'Missing data in session, cannot continue')
                return HttpResponseRedirect('.')
            try:
                tokens = TwitterSetup.authorize(request.session.pop('ownerkey'),
                                                request.session.pop('ownersecret'),
                                                request.POST.get('pincode'),
                )
            except:
                messages.error(request, 'Failed to get tokens from twitter.')
                return HttpResponseRedirect('.')

            conference.twitter_token = tokens.get('oauth_token')
            conference.twitter_secret = tokens.get('oauth_token_secret')
            conference.twittersync_active = False
            conference.save()
            messages.info(request, 'Twitter integration enabled')
            return HttpResponseRedirect('.')
        elif request.POST.get('deactivate_twitter', '') == '1':
            conference.twitter_token = ''
            conference.twitter_secret = ''
            conference.twittersync_active = False
            conference.save()
            messages.info(request, 'Twitter integration disabled')
            return HttpResponseRedirect('.')
        elif request.POST.get('test_twitter', '') == '1':
            testform = TwitterTestForm(data=request.POST)
            if testform.is_valid():
                tw = Twitter(conference)
                recipient = testform.cleaned_data['recipient']
                message = testform.cleaned_data['message']

                ok, code, msg = tw.send_message(recipient, message)
                if ok:
                    messages.info(request, 'Message successfully sent to {0}'.format(recipient))
                elif code == 150:
                    messages.warning(request, 'Cannot send message to users not being followed')
                else:
                    messages.error(request, 'Failed to send to {0}: {1}'.format(recipient, msg))
                return HttpResponseRedirect('.')
            form = TwitterForm(instance=conference)
        else:
            form = TwitterForm(instance=conference, data=request.POST)
            if form.is_valid():
                form.save()
                return HttpResponseRedirect('.')
    else:
        form = TwitterForm(instance=conference)
        testform = TwitterTestForm()

    return render(request, 'confreg/admin_integ_twitter.html', {
        'conference': conference,
        'form': form,
        'testform': testform,
        'helplink': 'integrations#twitter',
    })


class DelimitedWriter(object):
    def __init__(self, delimiter):
        self.delimiter = delimiter
        self.response = HttpResponse(content_type='text/plain; charset=utf-8')
        self.writer = csv.writer(self.response, delimiter=delimiter)

    def writeloaded(self):
        self.writer.writerow(["File loaded", datetime.datetime.now()])

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
        self.d['FileLoaded'] = datetime.datetime.now()

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
    conference = get_object_or_404(Conference, urlname=urlname)
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
        writer.columns(['Type', 'Confirmed', 'Unconfirmed'], True)
        writer.write_query("SELECT regtype, count(payconfirmedat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed FROM confreg_conferenceregistration r RIGHT JOIN confreg_registrationtype rt ON rt.id=r.regtype_id WHERE rt.conference_id=%(confid)s GROUP BY rt.id ORDER BY rt.sortkey", {'confid': conference.id, })
    elif datatype == 'discounts':
        writer.columns(['Code', 'Max uses', 'Confirmed', 'Unconfirmed'], True)
        writer.write_query("SELECT code, maxuses, count(payconfirmedat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed FROM confreg_conferenceregistration r RIGHT JOIN confreg_discountcode dc ON dc.code=r.vouchercode WHERE dc.conference_id=%(confid)s AND (r.conference_id=%(confid)s OR r.conference_id IS NULL) GROUP BY dc.id ORDER BY code", {'confid': conference.id, })
    elif datatype == 'vouchers':
        writer.columns(["Buyer", "Used", "Unused", "Purchased"])
        writer.write_query("SELECT b.buyername, count(v.user_id) AS used, count(*) FILTER (WHERE v.user_id IS NULL) AS unused,  EXISTS (SELECT 1 FROM confsponsor_purchasedvoucher pv WHERE pv.batch_id=b.id)::int AS purchased FROM confreg_prepaidbatch b INNER JOIN confreg_prepaidvoucher v ON v.batch_id=b.id WHERE b.conference_id=%(confid)s GROUP BY b.id ORDER BY buyername", {'confid': conference.id, })
    elif datatype == 'sponsors':
        (headers, data) = get_sponsor_dashboard_data(conference)
        writer.columns(headers, True)
        writer.write_rows(data)
    elif datatype == 'addopts':
        writer.columns(['Option', 'Confirmed', 'Unconfirmed', 'Remaining'])
        writer.write_query("SELECT ao.name, count(payconfirmedat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed, CASE WHEN maxcount>0 THEN maxcount ELSE NULL END-count(r.id) AS remaining FROM confreg_conferenceadditionaloption ao LEFT JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceadditionaloption_id=ao.id LEFT JOIN confreg_conferenceregistration r ON r.id=rao.conferenceregistration_id WHERE ao.conference_id=%(confid)s GROUP BY ao.id ORDER BY ao.name", {'confid': conference.id})
    else:
        raise Http404()

    return writer.response


def _attendee_email_form(request, conference, query, breadcrumbs):
    if request.method == 'POST':
        idlist = list(map(int, request.POST['idlist'].split(',')))
    else:
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
                    mailid = exec_to_scalar("INSERT INTO confreg_attendeemail (conference_id, sentat, subject, message) VALUES (%(confid)s, CURRENT_TIMESTAMP, %(subject)s, %(message)s) RETURNING id", {
                        'confid': conference.id,
                        'subject': form.cleaned_data['subject'],
                        'message': form.cleaned_data['message'],
                    })
                for r in recipients:
                    if form.cleaned_data['storeonregpage']:
                        msgtxt = "{0}\n\n-- \nThis message was sent to attendees of {1}.\nYou can view all communications for this conference at:\n{2}/events/{3}/register/\n".format(form.cleaned_data['message'], conference, settings.SITEBASE, conference.urlname)
                    else:
                        msgtxt = "{0}\n\n-- \nThis message was sent to attendees of {1}.\n".format(form.cleaned_data['message'], conference)
                    send_simple_mail(conference.contactaddr,
                                     r['email'],
                                     "[{0}] {1}".format(conference, form.cleaned_data['subject']),
                                     msgtxt,
                                     sendername=conference.conferencename,
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
                    messages.info(request, "Email sent to %s attendees, and added to registration pages when possible" % len(recipients))
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
