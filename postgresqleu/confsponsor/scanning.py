from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.conf import settings

import csv
import json
import re

from postgresqleu.util.random import generate_random_token
from postgresqleu.util.qr import generate_base64_qr
from postgresqleu.util.db import exec_to_dict, exec_to_keyed_scalar
from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.confreg.util import send_conference_mail, get_conference_or_404, render_conference_response

from .views import _get_sponsor_and_admin, get_authenticated_conference
from .models import SponsorScanner, ScannedAttendee
from .models import SponsorClaimedBenefit
from .benefitclasses import get_benefit_id


def testcode(request):
    return render(request, 'confsponsor/scanning_testcode.html', {
        'qrtest': generate_base64_qr('{}/t/at/TESTTESTTESTTEST/'.format(settings.SITEBASE), 2, 150),
    })


# Sponsor dashboard for badge scanning
@transaction.atomic
def sponsor_scanning(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request, False)

    if not sponsor.conference.askbadgescan:
        return HttpResponse("Badge scanning questions are not enabled on this conference", status=403)

    if not SponsorClaimedBenefit.objects.filter(sponsor=sponsor,
                                                benefit__benefit_class=get_benefit_id('badgescanning.BadgeScanning'),
                                                declined=False,
                                                confirmed=True).exists():
        return HttpResponse("Badge scanning not a claimed benefit for this sponsor", status=403)

    if request.method == 'POST':
        if request.POST.get('what', '') == 'add':
            if not request.POST.get('email', ''):
                messages.warning(request, "Cannot add empty address")
                return HttpResponseRedirect(".")
            try:
                reg = ConferenceRegistration.objects.get(conference=sponsor.conference, email=request.POST.get('email').lower())
                if not reg.payconfirmedat:
                    messages.error(request, "Attendee is not confirmed")
                    return HttpResponseRedirect(".")
                if reg.canceledat:
                    messages.error(request, "Attendee registration is canceled")
                    return HttpResponseRedirect(".")
                if sponsor.sponsorscanner_set.filter(scanner=reg).exists():
                    messages.warning(request, "Attendee already registered as a scanner")
                    return HttpResponseRedirect(".")
                if reg.attendee is None:
                    messages.warning(request, "Attendee does not have a connected account and must connect one before they can become a scanner")
                    return HttpResponseRedirect(".")
                scanner = SponsorScanner(sponsor=sponsor, scanner=reg, token=generate_random_token())
                scanner.save()
                sponsor.sponsorscanner_set.add(scanner)
                return HttpResponseRedirect(".")
            except ConferenceRegistration.DoesNotExist:
                messages.error(request, "Attendee not found")
                return HttpResponseRedirect(".")
        elif request.POST.get('what', '') == 'del':
            # There should only be one remove-<something>
            for k in request.POST.keys():
                if k.startswith('remove-'):
                    rid = k[len('remove-'):]
                    try:
                        scanner = SponsorScanner.objects.get(sponsor=sponsor, pk=rid)
                        n = scanner.scanner.fullname
                        if scanner.scanner.scanned_attendees.filter(sponsor=sponsor).exists():
                            messages.warning(request, "Attendee {0} has scanned badges already, cannot be removed".format(n))
                        else:
                            scanner.delete()
                            messages.info(request, "Attendee {0} removed from scanning".format(n))
                    except SponsorScanner.DoesNotExist:
                        messages.error(request, "Attendee not found")
                    return HttpResponseRedirect(".")
                elif k.startswith('email-'):
                    rid = k[len('email-'):]
                    try:
                        scanner = SponsorScanner.objects.get(sponsor=sponsor, pk=rid)
                        send_conference_mail(
                            sponsor.conference,
                            scanner.scanner.email,
                            "Attendee badge scanning",
                            "confsponsor/mail/badge_scanning_intro.txt",
                            {
                                'conference': sponsor.conference,
                                'sponsor': sponsor,
                                'scanner': scanner,
                            },
                            sender=sponsor.conference.sponsoraddr,
                            receivername=scanner.scanner.fullname,
                        )
                        messages.info(request, "Instructions email sent to {0}".format(scanner.scanner.fullname))
                    except SponsorScanner.DoesNotExist:
                        messages.error(request, "Attendee not found")
                    return HttpResponseRedirect(".")
            else:
                messages.error(request, "Invalid form submit")
                return HttpResponseRedirect(".")
        elif request.POST.get('what', '') == 'delscan':
            # There should only be one delete-scan-<id>
            for k in request.POST.keys():
                if k.startswith('delete-scan-'):
                    scid = int(k[len('delete-scan-'):])
                    try:
                        scan = ScannedAttendee.objects.get(sponsor=sponsor, pk=scid)
                        scan.delete()
                    except ScannedAttendee.DoesNotExist:
                        messages.error(request, "Scan has already been removed or permission denied")
                    break
            else:
                messages.error(request, "Invalid form submit")
            return HttpResponseRedirect(".")
        else:
            # Unknown form, so just return
            return HttpResponseRedirect(".")

    scanned = ScannedAttendee.objects.select_related('attendee', 'scannedby', 'attendee__country').filter(sponsor=sponsor)

    return render(request, 'confsponsor/sponsor_scanning.html', {
        'scanners': sponsor.sponsorscanner_set.all(),
        'scanned': scanned,
    })


def sponsor_scanning_download(request, sponsorid):
    sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request, False)

    if not sponsor.conference.askbadgescan:
        return HttpResponse("Badge scanning questions are not enabled on this conference", status=403)

    if not SponsorClaimedBenefit.objects.filter(sponsor=sponsor,
                                                benefit__benefit_class=get_benefit_id('badgescanning.BadgeScanning'),
                                                declined=False,
                                                confirmed=True).exists():
        return HttpResponse("Badge scanning not a claimed benefit for this sponsor", status=403)

    scanned = ScannedAttendee.objects.select_related('attendee', 'scannedby', 'attendee__country').filter(sponsor=sponsor)

    response = HttpResponse(content_type='text/csv; charset=utf8')
    response['Content-Disposition'] = 'attachment;filename=scanned_users.csv'
    c = csv.writer(response)
    c.writerow(['Attendee name', 'Attendee country', 'Attendee company', 'Attendee email', 'Scanned at', 'Scanned by', 'Scan note'])
    for s in scanned:
        c.writerow([s.attendee.fullname, s.attendee.country, s.attendee.company, s.attendee.email, s.scannedat, s.scannedby.fullname, s.note])

    return response


# Render the scanning app from the scanner token
def _sponsor_scanning_page(request, scanner, extra=None):
    c = {
        'scanner': scanner,
        'sponsor': scanner.sponsor,
        'conference': scanner.sponsor.conference,
        'title': 'badge scan',
        'doing': 'Scan badge',
        'scanwhat': 'badge',
        'scannertype': 'Sponsor',
        'storebutton': 'Scan',
        'expectedtype': 'at',
        'hasnote': True,
        'scanfields': [
            ["name", "Name"],
            ["company", "Company"],
            ["country", "Country"],
            ["email", "E-mail"],
        ],
        'tokentype': 'at',
    }
    if extra:
        c.update(extra)

    return render(request, 'confreg/scanner_app.html', c)


def scanning_page(request, scannertoken):
    try:
        scanner = SponsorScanner.objects.select_related('sponsor', 'sponsor__conference').get(token=scannertoken)
    except SponsorScanner.DoesNotExist:
        raise Http404("Not found")

    return _sponsor_scanning_page(request, scanner)


# Landing page with instructions for how to start the scanning app
@login_required
def landing(request, urlname):
    conference = get_conference_or_404(urlname)
    try:
        reg = ConferenceRegistration.objects.get(conference=conference, attendee=request.user, payconfirmedat__isnull=False, canceledat__isnull=True)
    except ConferenceRegistration.DoesNotExist:
        raise Http404("You are not registered for this conference")

    # If we have a token, use that to identify which sponsor is being represented.
    # If we don't have a token, get all scanner setups for this user. If that is just
    # one sponsor, send the user directly there. If it's >1, show the page to select
    # which sponsor to represent, which will redirect to a token-included URL.
    scanners = SponsorScanner.objects.filter(sponsor__conference=conference, scanner=reg)
    if 'token' in request.GET:
        scanners = scanners.filter(token=request.GET['token'])

    scanners = list(scanners)
    if len(scanners) == 0:
        raise Http404("You are not registered as a scanner for any sponsor at this conference")
    elif len(scanners) > 1:
        return render_conference_response(request, conference, 'reg', 'confsponsor/scanner_selectsponsor.html', {
            'conference': conference,
            'scanners': scanners,
        })
    else:
        scanner = scanners[0]

    link = '{}/events/sponsor/scanning/{}/'.format(settings.SITEBASE, scanner.token)
    return render_conference_response(request, conference, 'reg', 'confsponsor/scanner_landing.html', {
        'conference': conference,
        'sponsor': scanner.sponsor,
        'scannerlink': link,
        'qrlink': generate_base64_qr(link, 5, 200),
        'qrtest': generate_base64_qr('{}/t/at/TESTTESTTESTTEST/'.format(settings.SITEBASE), 2, 150),
    })


# Called from confreg/checkin.py when directly scanning a token without using the app
class SponsorScannerHandler:
    def __init__(self, sponsorscanner):
        self.scanner = sponsorscanner

    def launch(self, request, scanned_token):
        return _sponsor_scanning_page(request, self.scanner, {
            'singletoken': scanned_token,
            'basehref': '{}/events/sponsor/scanning/{}/'.format(settings.SITEBASE, self.scanner.token),
        })

    @property
    def title(self):
        return 'Sponsor: {}'.format(self.scanner.sponsor.displayname)


def _json_response(reg, status, existingnote='', message=''):
    return HttpResponse(json.dumps({
        'reg': {
            'name': reg.fullname,
            'company': reg.company,
            'country': reg.country and reg.country.printable_name or '',
            'email': reg.email,
            'note': existingnote,
            'token': reg.publictoken,
            'highlight': [],
        },
        'message': message,
        'showfields': False,
    }), content_type='application/json', status=status)


_tokenmatcher = re.compile('^{}/t/at/([^/]+)/$'.format(settings.SITEBASE))


def _get_scanned_attendee(sponsor, token):
    try:
        attendee = ConferenceRegistration.objects.get(conference=sponsor.conference, publictoken=token)
    except ConferenceRegistration.DoesNotExist:
        return HttpResponse("Attendee not found", status=404)

    if not attendee.badgescan:
        return HttpResponse("Attendee has not authorized badge scanning", status=403)

    if attendee.canceledat:
        return HttpResponse("Attendee registration is canceled", status=403)

    return attendee


@csrf_exempt
@global_login_exempt
def scanning_api(request, scannertoken, what):
    try:
        scanner = SponsorScanner.objects.select_related('sponsor', 'sponsor__conference', 'scanner', 'scanner__attendee').get(token=scannertoken)
    except SponsorScanner.DoesNotExist:
        raise Http404("Not found")

    sponsor = scanner.sponsor

    if request.method in ('GET', 'POST'):
        if what == 'status':
            # Request for status is handled separately, everything else is a scan
            return HttpResponse(json.dumps({
                'scanner': scanner.scanner.attendee.username,
                'name': '{} for {}'.format(scanner.scanner.fullname, scanner.sponsor.displayname),
                'sponsorname': scanner.sponsor.displayname,
                'confname': scanner.sponsor.conference.conferencename,
                'active': True,  # As soon as badges are available they can be scanned.
                'admin': False,  # There are no "admins" in badge scanning
                'activestatus': '',
            }), content_type='application/json')
        elif what == 'lookup':
            token = request.GET.get('lookup')
            m = _tokenmatcher.match(token)
            if m:
                token = m.group(1)
            else:
                raise Http404()

            with transaction.atomic():
                r = _get_scanned_attendee(sponsor, token)
                if isinstance(r, HttpResponse):
                    return r

                # Mark the badge as scanned already on search. The POST later can change the note,
                # but we record it regardless
                scan, created = ScannedAttendee.objects.get_or_create(sponsor=sponsor, scannedby=scanner.scanner, attendee=r)

                if not created and scan.firstscan:
                    # An already existing entry which was flagged as first. That likely means that someone forgot the "save" button on the previous
                    # scan. So we set it to no-longer-first, so we get the update information on the next try.
                    scan.firstscan = False
                    scan.save(update_fields=['firstscan'])

                return _json_response(r, 200, scan.note, 'Attendee {} scan stored successfully.'.format(r.fullname))
        elif request.method == 'POST' and what == 'store':
            with transaction.atomic():
                # Accept both full URL version of token and just the key part
                m = _tokenmatcher.match(request.POST['token'])
                if m:
                    token = m.group(1)
                else:
                    token = request.POST['token']
                r = _get_scanned_attendee(sponsor, token)
                if isinstance(r, HttpResponse):
                    return r

                scan, created = ScannedAttendee.objects.get_or_create(sponsor=sponsor, scannedby=scanner.scanner, attendee=r, defaults={'note': request.POST.get('note')})
                if created:
                    # This would normally never happen anymore as we create the record on search. Only if someone deletes it in between.
                    return _json_response(attendee, 201)
                else:
                    update = []
                    isfirst = scan.firstscan

                    if scan.note != request.POST.get('note'):
                        scan.note = request.POST.get('note')
                        update.append('note')

                    if scan.firstscan:
                        scan.firstscan = False
                        update.append('firstscan')
                    if update:
                        scan.save(update_fields=update)
                    return _json_response(
                        r,
                        201 if isfirst else 208,
                        scan.note,
                        'Attendee {} scan stored successfully.'.format(r.fullname) if isfirst else 'Attendee {} has already been stored.{}'.format(
                            r.fullname,
                            'The note has been updated.' if 'note' in update else '',
                        ),
                    )
        else:
            raise Http404()
    else:
        return HttpResponse("Invalid method", status=400)


def admin_scan_status(request, confurlname):
    conference = get_authenticated_conference(request, confurlname)

    if not conference.askbadgescan:
        return HttpResponse("Badge scanning not active")

    uniquebysponsor = exec_to_keyed_scalar("""
SELECT
  sp.id AS sponsorid,
  count(DISTINCT sa.attendee_id) AS num
FROM confsponsor_sponsorscanner sc
INNER JOIN confsponsor_sponsor sp ON sc.sponsor_id=sp.id
LEFT JOIN confsponsor_scannedattendee sa ON sa.sponsor_id=sp.id
WHERE sp.conference_id=%(confid)s
GROUP BY sp.id""", {
        'confid': conference.id,
    })

    uniquebyscanner = exec_to_dict("""
SELECT
  sp.id AS sponsorid,
  sp.name AS sponsorname,
  r.email,
  count(DISTINCT sa.attendee_id) AS num
FROM confsponsor_sponsorscanner sc
INNER JOIN confsponsor_sponsor sp ON sc.sponsor_id=sp.id
INNER JOIN confsponsor_sponsorshiplevel l ON sp.level_id=l.id
INNER JOIN confreg_conferenceregistration r ON r.id=sc.scanner_id
LEFT JOIN confsponsor_scannedattendee sa ON sa.sponsor_id=sp.id AND sa.scannedby_id=r.id
WHERE sp.conference_id=%(confid)s
GROUP BY sp.id, sp.name, l.id, r.email
ORDER BY l.levelcost DESC, l.levelname, sp.name, r.email
""", {
        'confid': conference.id,
    })

    return render(request, 'confsponsor/admin_scanstatus.html', {
        'conference': conference,
        'uniquebysponsor': uniquebysponsor,
        'scans': uniquebyscanner,
        'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
    })
