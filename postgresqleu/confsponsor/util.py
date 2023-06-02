from django.db.models import Q
from django.conf import settings

from postgresqleu.util.db import exec_to_list
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.confreg.util import send_conference_mail
from postgresqleu.confsponsor.models import SponsorMail


def get_sponsor_dashboard_data(conference):
    return (
        ["Level", "Confirmed", "Unconfirmed"],
        exec_to_list("SELECT l.levelname, count(s.id) FILTER (WHERE confirmed) AS confirmed, count(s.id) FILTER (WHERE NOT confirmed) AS unconfirmed FROM confsponsor_sponsorshiplevel l LEFT JOIN confsponsor_sponsor s ON s.level_id=l.id WHERE l.conference_id=%(confid)s GROUP BY l.id ORDER BY levelcost", {'confid': conference.id, })
    )


def send_conference_sponsor_notification(conference, subject, message):
    if conference.sponsoraddr:
        send_simple_mail(conference.sponsoraddr,
                         conference.sponsoraddr,
                         subject,
                         message,
                         sendername=conference.conferencename)


def send_sponsor_manager_email(sponsor, subject, template, context, attachments=None):
    for manager in sponsor.managers.all():
        send_conference_mail(
            sponsor.conference,
            manager.email,
            subject,
            template,
            context,
            attachments=attachments,
            sender=sponsor.conference.sponsoraddr,
            sendername=sponsor.conference.conferencename,
            receivername='{0} {1}'.format(manager.first_name, manager.last_name)
        )


def get_mails_for_sponsor(sponsor):
    return SponsorMail.objects.filter(
        Q(conference=sponsor.conference),
        Q(levels=sponsor.level) | Q(sponsors=sponsor)
    )


def get_pdf_fields_for_conference(conference, sponsor=None):
    fields = [
        ('static:sponsor', sponsor.name if sponsor else 'Sponsor company name'),
    ]
    if settings.EU_VAT:
        fields.append(
            ('static:euvat', sponsor.vatnumber if sponsor else 'Sponsor EU VAT number'),
        )

    return fields
