from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db import transaction

import csv
import json

from postgresqleu.util.random import generate_random_token
from postgresqleu.util.qr import generate_base64_qr
from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.confreg.util import send_conference_mail

from .views import _get_sponsor_and_admin
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
def scanning_api(request, scannertoken):
    try:
        scanner = SponsorScanner.objects.select_related('sponsor', 'sponsor__conference').get(token=scannertoken)
    except SponsorScanner.DoesNotExist:
        raise Http404("Not found")

    sponsor = scanner.sponsor

    if request.method in ('GET', 'POST'):
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
                # If already scanned by the same scanner, then provide a default value for the
                # note field.
                qq = attendee.scanned_by.filter(scannedby=scanner)[:1]
                if qq:
                    existingnote = qq[0].note
                else:
                    existingnote = ''

                return _json_response(attendee, 200, existingnote)
            elif request.method == 'POST':
                scan, created = ScannedAttendee.objects.get_or_create(sponsor=sponsor, scannedby=scanner.scanner, attendee=attendee, defaults={'note': request.POST.get('note')})
                if created:
                    scan.save()
                    return _json_response(attendee, 201)
                else:
                    return _json_response(attendee, 208)
    else:
        return HttpResponse("Invalid method", status=400)
