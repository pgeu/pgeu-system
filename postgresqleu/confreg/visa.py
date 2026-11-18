import os
from io import BytesIO
from datetime import datetime

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import escape

import jinja2

from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from postgresqleu.util.image import rescale_image_bytes

from .models import Conference, ConferenceRegistration, VisaLetterRequest
from .util import get_authenticated_conference, render_conference_response


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VISA_LETTER_TEMPLATE_PATH = os.path.join(PROJECT_ROOT, 'template', 'confreg', 'visa_letter_template.j2')


def _is_speaker(registration):
    return registration.conference.conferencesession_set.filter(
        speaker__user=registration.attendee, status__in=[1, 4]).exists()


def is_visa_eligible(registration):
    return (
        registration.payconfirmedat is not None or
        registration.is_volunteer or
        (registration.regtype and registration.regtype.specialtype in ('staff', 'spk', 'spkr')) or
        _is_speaker(registration)
    )


class VisaLetterRequestForm(forms.ModelForm):
    class Meta:
        model = VisaLetterRequest
        fields = [
            'passport_name', 'passport_sex', 'date_of_birth', 'passport_number', 'nationality',
            'home_address', 'embassy_name', 'embassy_address',
            'entry_date', 'exit_date', 'accommodation', 'contact_info',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'entry_date': forms.DateInput(attrs={'type': 'date'}),
            'exit_date': forms.DateInput(attrs={'type': 'date'}),
            'passport_name': forms.TextInput(attrs={'size': 60}),
            'embassy_name': forms.TextInput(attrs={'size': 60}),
            'accommodation': forms.TextInput(attrs={'size': 60}),
            'contact_info': forms.TextInput(attrs={'size': 60}),
        }

    def clean(self):
        cleaned = super().clean()
        conf = self.instance.conference
        entry = cleaned.get('entry_date')
        exit_ = cleaned.get('exit_date')
        if entry:
            if entry > conf.enddate:
                self.add_error('entry_date', 'Entry date must be before or during the conference.')
            elif conf.startdate.toordinal() - entry.toordinal() > 30:
                self.add_error('entry_date', 'Entry date must not be more than a month before the conference starts.')
        if exit_:
            if exit_ < conf.startdate:
                self.add_error('exit_date', 'Exit date must be during or after the conference.')
            elif exit_.toordinal() - conf.enddate.toordinal() > 30:
                self.add_error('exit_date', 'Exit date must not be more than a month after the conference ends.')
        return cleaned


@login_required
@transaction.atomic
def visa_letter(request, confname):
    conference = get_object_or_404(Conference, urlname=confname)
    if not conference.visa_letter_enabled:
        raise Http404
    try:
        registration = ConferenceRegistration.objects.get(
            conference=conference, attendee=request.user, canceledat__isnull=True)
    except ConferenceRegistration.DoesNotExist:
        messages.error(request, "You must have a registration for this conference to request a visa letter.")
        return redirect('/events/{}/'.format(confname))
    if not is_visa_eligible(registration):
        messages.error(request, "Visa letters are available to attendees with full payment confirmed, speakers, volunteers, and conference staff.")
        return redirect('/events/{}/'.format(confname))

    visa_request = VisaLetterRequest.objects.filter(
        conference=conference, registration=registration).first()
    editable = visa_request is None or visa_request.status == VisaLetterRequest.STATUS_CHANGES_NEEDED
    form = None
    if editable:
        instance = visa_request or VisaLetterRequest(conference=conference, registration=registration)
        if request.method == 'POST':
            form = VisaLetterRequestForm(request.POST, instance=instance)
            if form.is_valid():
                obj = form.save(commit=False)
                if visa_request is not None:
                    obj.status = VisaLetterRequest.STATUS_PENDING
                obj.save()
                messages.success(request, "Your visa letter request has been submitted for review.")
                return redirect('.')
        else:
            form = VisaLetterRequestForm(instance=instance)

    return render_conference_response(request, conference, 'reg', 'confreg/visa_letter.html', {
        'form': form,
        'visa_request': visa_request,
    })


def admin_visa_letter_generate(request, urlname, requestid):
    conference = get_authenticated_conference(request, urlname)
    visa_request = get_object_or_404(
        VisaLetterRequest,
        id=requestid,
        conference=conference,
        status=VisaLetterRequest.STATUS_APPROVED,
    )
    if request.method != 'POST':
        return redirect('../')

    sig = request.FILES.get('signature')
    if not sig:
        messages.error(request, "Please upload a signature image.")
    elif not sig.content_type.startswith('image/'):
        messages.error(request, "The uploaded file must be an image (PNG or JPEG).")
    elif sig.size > 2 * 1024 * 1024:
        messages.error(request, "The signature image must be smaller than 2 MB.")
    else:
        pdf_bytes = generate_visa_letter_pdf(visa_request, sig.read())
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="visa_letter_{}_{}.pdf"'.format(
            conference.urlname, visa_request.registration.lastname)
        return response
    return redirect('../')


def _render_letter_body(visa_request):
    conference = visa_request.conference
    if conference.startdate == conference.enddate:
        confdates = conference.startdate.strftime('%B %d, %Y')
    else:
        confdates = '{} – {}'.format(
            conference.startdate.strftime('%B %d'),
            conference.enddate.strftime('%B %d, %Y'),
        )
    is_speaker = _is_speaker(visa_request.registration)

    with open(VISA_LETTER_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = jinja2.Template(f.read())
    return template.render(
        conference={
            'name': conference.conferencename,
            'dates': confdates,
            'venue': conference.location,
            'city': conference.visa_letter_city,
            'country': conference.visa_letter_country,
        },
        full_name_passport=visa_request.passport_name,
        passport_sex=visa_request.passport_sex,
        date_of_birth=visa_request.date_of_birth.strftime('%d/%m/%Y'),
        nationality=visa_request.nationality,
        passport_number=visa_request.passport_number,
        address=visa_request.home_address,
        entry_date=visa_request.entry_date.strftime('%d/%m/%Y'),
        exit_date=visa_request.exit_date.strftime('%d/%m/%Y'),
        stay_at=visa_request.accommodation,
        contact=visa_request.contact_info,
        is_speaker=is_speaker,
        accommodation_covered=visa_request.accommodation_covered,
        signer={'signature_text': conference.visa_letter_signer},
    )


def generate_visa_letter_pdf(visa_request, signature_bytes):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=10, leading=12, spaceAfter=6)
    right = ParagraphStyle('right', parent=body, alignment=TA_RIGHT)

    today = datetime.now().strftime('%B %d, %Y')
    story = []

    from PIL import Image as PILImage
    logo_path = os.path.join(PROJECT_ROOT, 'media', 'img', 'pgeu_logo.png')
    with PILImage.open(logo_path) as _img:
        ratio = _img.size[0] / _img.size[1]
    target_height = 0.85 * inch
    logo_element = Image(logo_path, width=target_height * ratio, height=target_height)
    logo_element.hAlign = 'LEFT'
    address_html = (
        '<b>PostgreSQL Europe</b><br/>'
        '61, rue de Lyon<br/>'
        '75012 PARIS<br/>'
        'FRANCE<br/>'
        'Website: https://www.postgresql.eu/<br/>'
        'Email: board@postgresql.eu'
    )
    story.append(Table(
        [[logo_element, Paragraph(address_html, body)]],
        colWidths=[4.0 * inch, 2.25 * inch],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    story.append(Spacer(1, 24))

    embassy_html = '{}<br/>{}'.format(
        escape(visa_request.embassy_name),
        escape(visa_request.embassy_address).replace('\n', '<br/>'),
    )
    story.append(Table(
        [[Paragraph(embassy_html, body), Paragraph(today, right)]],
        colWidths=[3.5 * inch, 2.5 * inch],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    story.append(Spacer(1, 20))

    scaled = rescale_image_bytes(signature_bytes, (250, 100))
    letter_content = _render_letter_body(visa_request)
    for para in letter_content.strip().split('\n\n'):
        chunk = para.strip()
        if not chunk:
            continue
        if '[SIGNATURE_PLACEHOLDER]' in chunk:
            before, after = chunk.split('[SIGNATURE_PLACEHOLDER]', 1)
            if before.strip():
                story.append(Paragraph(before.strip().replace('\n', ' '), body))
                story.append(Spacer(1, 6))
            sig = Image(BytesIO(scaled), width=2.2 * inch, height=0.9 * inch)
            sig.hAlign = 'LEFT'
            story.append(sig)
            story.append(Spacer(1, 6))
            if after.strip():
                story.append(Paragraph(after.strip().replace('\n', '<br/>'), body))
        else:
            story.append(Paragraph(chunk.replace('\n', ' '), body))

    doc.build(story)
    return buf.getvalue()
