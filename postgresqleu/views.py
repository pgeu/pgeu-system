# Index has a very special view that lives out here
from django.shortcuts import render, get_object_or_404
from django.template.defaultfilters import slugify
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings

from postgresqleu.confreg.models import Conference, ConferenceSeries
from postgresqleu.invoices.models import PendingBankTransaction, BankFileUpload, InvoicePaymentMethod
from postgresqleu.invoices.models import InvoiceRefund

from postgresqleu.util.db import exec_to_dict, conditional_exec_to_scalar
from postgresqleu.util.time import today_global

import datetime
import markdown


# Handle the frontpage
def index(request):
    events = Conference.objects.filter(promoactive=True, enddate__gte=today_global()).order_by('startdate')
    series = ConferenceSeries.objects.filter(visible=True).extra(
        where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
    )

    # Native query, because django ORM vs UNION...
    # If a news item has the flag "high priority until" until a date that's still in the future,
    # make sure it always bubbles to the top of the list. We do this by creating a secondary ordering
    # field to order by first. To make sure we capture all such things, we need to get at least the
    # same number of items from each subset and then LIMIT it once again for the total limit.
    news = exec_to_dict("""WITH main AS (
  SELECT id, NULL::text AS confurl, NULL::text AS urlname, CASE WHEN highpriorityuntil > CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS priosort, datetime, title, summary
  FROM newsevents_news
  WHERE datetime<CURRENT_TIMESTAMP ORDER BY datetime DESC LIMIT 5),
conf AS (
  SELECT n.id, c.confurl, c.urlname, 0 AS priosort, datetime, c.conferencename || ': ' || title AS title, summary
  FROM confreg_conferencenews n
  INNER JOIN confreg_conference c ON c.id=conference_id
  WHERE datetime<CURRENT_TIMESTAMP
  ORDER BY datetime DESC LIMIT 5)
SELECT id, confurl, urlname, datetime, title, summary, priosort FROM main
UNION ALL
SELECT id, confurl, urlname, datetime, title, summary, priosort FROM conf
ORDER BY priosort DESC, datetime DESC LIMIT 5""")
    for n in news:
        n['summaryhtml'] = markdown.markdown(n['summary'])
        if n['confurl']:
            n['itemlink'] = '/events/{0}/news/{1}-{2}/'.format(
                n['urlname'],
                slugify(n['title']),
                n['id'],
            )
        else:
            n['itemlink'] = '/news/{0}-{1}/'.format(slugify(n['title']), n['id'])

    return render(request, 'index.html', {
        'events': events,
        'series': series,
        'news': news,
    })


# Handle the events frontpage
def eventsindex(request):
    events = list(Conference.objects.filter(promoactive=True, enddate__gte=today_global()).order_by('startdate'))
    past = Conference.objects.filter(promoactive=True, enddate__lt=today_global()).order_by('-startdate')[:5]
    series = ConferenceSeries.objects.filter(visible=True).extra(
        where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
    )

    return render(request, 'events/index.html', {
        'events': events,
        'past': past,
        'series': series,
        'regopen': [e for e in events if e.registrationopen],
        'cfpopen': [e for e in events if e.IsCallForPapersOpen],
        'cfsopen': [e for e in events if e.IsCallForSponsorsOpen],
    })


# Handle past events list
def pastevents(request):
    events = list(Conference.objects.filter(promoactive=True, enddate__gte=today_global()).order_by('startdate'))
    past = Conference.objects.filter(promoactive=True, enddate__lt=today_global()).order_by('-startdate')
    series = ConferenceSeries.objects.filter(visible=True).extra(
        where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
    )

    return render(request, 'events/past.html', {
        'events': events,
        'past': past,
        'series': series,
    })


# Handle event series listing
def eventseries(request, id):
    series = get_object_or_404(ConferenceSeries, pk=id)
    events = list(series.conference_set.filter(promoactive=True).order_by('startdate'))

    return render(request, 'events/series.html', {
        'series': series,
        'upcoming': [e for e in events if e.enddate >= today_global()],
        'past': [e for e in events if e.enddate < today_global()],
    })


# Handle a users list of previous events
@login_required
def attendee_events(request):
    events = list(Conference.objects.filter(promoactive=True, enddate__gte=today_global()).order_by('startdate'))
    series = ConferenceSeries.objects.filter(visible=True).extra(
        where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
    )
    attended = Conference.objects.only('urlname', 'conferencename', 'location').filter(conferenceregistration__attendee=request.user, conferenceregistration__payconfirmedat__isnull=False).distinct().order_by('-startdate')
    return render(request, 'events/attendee.html', {
        'attended': attended,
        'events': events,
        'series': series,
    })


@login_required
def admin_dashboard(request):
    if request.user.is_superuser:
        permissions = {
            'conferences': True,
            'news': True,
            'membership': settings.ENABLE_MEMBERSHIP,
            'elections': settings.ENABLE_ELECTIONS,
            'invoices': True,
            'accounting': True,
        }
    else:
        groups = [g.name for g in request.user.groups.all()]
        confperm = ConferenceSeries.objects.filter(administrators=request.user).exists() or Conference.objects.filter(administrators=request.user).exists()

        permissions = {
            'conferences': confperm,
            'news': 'News administrators' in groups,
            'membership': settings.ENABLE_MEMBERSHIP and 'Membership administrators' in groups,
            'elections': settings.ENABLE_ELECTIONS and 'Election administrators' in groups,
            'invoices': "Invoice managers" in groups,
            'accounting': "Accounting managers" in groups,
        }

    if permissions['invoices']:
        pending_bank = PendingBankTransaction.objects.all().exists()
        pending_refunds = InvoiceRefund.objects.filter(completed__isnull=True).exists()
        ipm = list(InvoicePaymentMethod.objects.filter(active=True, config__has_key='file_upload_interval'))
        if ipm:
            # At least one payment method exists that *should* get uploads checked
            # XXX: this could probably be done more efficient... But we never have
            # many payment methods, and even fewer that actually handle file uploads.
            for pm in ipm:
                if pm.config['file_upload_interval'] > 0:
                    if not BankFileUpload.objects.filter(method=pm,
                                                         created__gt=timezone.now() - datetime.timedelta(days=pm.config['file_upload_interval'])
                    ).exists():
                        bank_file_uploads = True
                        break
            else:
                bank_file_uploads = False
        else:
            bank_file_uploads = None
    else:
        pending_bank = False
        pending_refunds = False
        bank_file_uploads = None

    return render(request, 'adm/index.html', {
        'permissions': permissions,
        'pending_bank': pending_bank,
        'pending_refunds': pending_refunds,
        'bank_file_uploads': bank_file_uploads,
        'schedalert': conditional_exec_to_scalar(request.user.is_superuser, "SELECT NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name='pgeu scheduled job runner' AND datname=current_database())"),
        'mailqueuealert': conditional_exec_to_scalar(request.user.is_superuser, "SELECT EXISTS (SELECT 1 FROM mailqueue_queuedmail LIMIT 1)"),
        'meetingserver': settings.ENABLE_MEMBERSHIP and settings.MEETINGS_STATUS_BASE_URL,
    })


# Handle CSRF failures
def csrf_failure(request, reason=''):
    resp = render(request, 'csrf_failure.html', {
        'reason': reason,
        })
    resp.status_code = 403  # Forbidden
    return resp
