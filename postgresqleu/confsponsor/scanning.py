from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db import transaction

import csv
import json

from postgresqleu.util.random import generate_random_token
from postgresqleu.util.qr import generate_base64_qr
from postgresqleu.util.db import exec_to_dict, exec_to_keyed_scalar
from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.confreg.util import send_conference_mail

from .views import _get_sponsor_and_admin, get_authenticated_conference
from .models import SponsorScanner, ScannedAttendee
from .models import SponsorClaimedBenefit
from .benefitclasses import get_benefit_id


def testcode(request):
    return render(request, 'confsponsor/scanning_testcode.html', {
        'qrtest': generate_base64_qr("AT$TESTTESTTESTTEST$AT", 2, 150),
    })


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
                if sponsor.sponsorscanner_set.filter(scanner=reg).exists():
                    messages.warning(request, "Attendee already registered as a scanner")
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
                        if scanner.scanner.scanned_attendees.exists():
                            messages.warning(request, "Attende {0} has scanned badges already, cannot be removed".format(n))
                        else:
                            scanner.delete()
                            messages.info(request, "Attendee {0} removed from scanning".format(n))
                    except SponsorScanner.DoesNotExist:
                        messges.error(request, "Attendee not found")
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

    response = HttpResponse(content_type='text/plain; charset=utf8')
    c = csv.writer(response, delimiter=';')
    c.writerow(['Attendee name', 'Attendee country', 'Attendee company', 'Attendee email', 'Scanned at', 'Scanned by', 'Scan note'])
    for s in scanned:
        c.writerow([s.attendee.fullname, s.attendee.country, s.attendee.company, s.attendee.email, s.scannedat, s.scannedby.fullname, s.note])

    return response


def scanning_page(request, scannertoken):
    try:
        scanner = SponsorScanner.objects.select_related('sponsor', 'sponsor__conference').get(token=scannertoken)
    except SponsorScanner.DoesNotExist:
        raise Http404("Not found")

    return render(request, 'confsponsor/scanner_app.html', {
        'scanner': scanner,
        'sponsor': scanner.sponsor,
        'conference': scanner.sponsor.conference,
    })


def _json_response(reg, status, existingnote=''):
    return HttpResponse(json.dumps({
        'name': reg.fullname,
        'company': reg.company,
        'country': reg.country and reg.country.printable_name or '',
        'email': reg.email,
        'note': existingnote,
    }), content_type='application/json', status=status)


@csrf_exempt
@global_login_exempt
def scanning_api(request, scannertoken):
    try:
        scanner = SponsorScanner.objects.select_related('sponsor', 'sponsor__conference', 'scanner', 'scanner__attendee').get(token=scannertoken)
    except SponsorScanner.DoesNotExist:
        raise Http404("Not found")

    sponsor = scanner.sponsor

    if request.method in ('GET', 'POST'):
        if request.GET.get('status', ''):
            # Request for status is handled separately, everything else is a scan
            return HttpResponse(json.dumps({
                'scanner': scanner.scanner.attendee.username,
                'name': scanner.scanner.fullname,
                'confname': scanner.sponsor.conference.conferencename,

            }), content_type='application/json')

        with transaction.atomic():
            token = request.GET.get('token', '') or request.POST.get('token', '')
            if not token:
                return HttpResponse("No search specified", status=404, content_type='text/plain')
            if not (token.startswith('AT$') and token.endswith('$AT')):
                return HttpResponse("Invalid type of token specified", status=404, content_type='text/plain')
            token = token[3:-3]
            try:
                attendee = ConferenceRegistration.objects.get(conference=sponsor.conference, publictoken=token)
            except ConferenceRegistration.DoesNotExist:
                return HttpResponse("Attendee not found", status=404)

            if not attendee.badgescan:
                return HttpResponse("Attendee has not authorized badge scanning", status=403)

            if request.method == 'GET':
                # Mark the badge as scanned already on search. The POST later can change the note,
                # but we record it regardless
                scan, created = ScannedAttendee.objects.get_or_create(sponsor=sponsor, scannedby=scanner.scanner, attendee=attendee)

                return _json_response(attendee, 200, scan.note)
            elif request.method == 'POST':
                scan, created = ScannedAttendee.objects.get_or_create(sponsor=sponsor, scannedby=scanner.scanner, attendee=attendee, defaults={'note': request.POST.get('note')})
                if created:
                    return _json_response(attendee, 201)
                else:
                    if scan.note != request.POST.get('note'):
                        scan.note = request.POST.get('note')
                        scan.save()
                    return _json_response(attendee, 208, scan.note)
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
