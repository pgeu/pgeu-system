from django.db.models import Q
from django.conf import settings

from postgresqleu.util.db import exec_to_list
from postgresqleu.util.currency import format_currency
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.confreg.util import send_conference_mail, send_conference_simple_mail
from postgresqleu.confsponsor.models import SponsorMail
from postgresqleu.confsponsor.models import SponsorshipLevel


def get_sponsor_dashboard_data(conference):
    return (
        ["Level", "Confirmed", "Unconfirmed"],
        exec_to_list("SELECT l.levelname, count(s.id) FILTER (WHERE confirmed) AS confirmed, count(s.id) FILTER (WHERE NOT confirmed) AS unconfirmed FROM confsponsor_sponsorshiplevel l LEFT JOIN confsponsor_sponsor s ON s.level_id=l.id WHERE l.conference_id=%(confid)s GROUP BY l.id ORDER BY levelcost", {'confid': conference.id, })
    )


def _get_benefit_data(b):
    yield 'name', b.benefitname
    yield 'sortkey', b.sortkey
    yield 'description', b.benefitdescription
    yield 'maxclaims', b.maxclaims
    if b.deadline:
        yield 'deadline', b.deadline


def sponsorleveldata(conference):
    overviewdata = exec_to_list("""WITH
 levels AS (SELECT id, levelname, levelcost FROM confsponsor_sponsorshiplevel WHERE conference_id=%(confid)s),
 all_names AS (SELECT DISTINCT b.overview_name FROM confsponsor_sponsorshipbenefit b INNER JOIN levels l ON l.id=b.level_id WHERE b.overview_name != ''),
 all_benefits As (SELECT overview_name, levels.id AS level_id, levelcost, levelname FROM all_names CROSS JOIN levels)
SELECT a.overview_name,
       array_agg(CASE WHEN b.overview_value != '' THEN b.overview_value ELSE maxclaims::text END ORDER BY levelcost DESC, levelname)
FROM all_benefits a
LEFT JOIN confsponsor_sponsorshipbenefit b ON b.overview_name=a.overview_name AND b.level_id=a.level_id
GROUP BY a.overview_name
ORDER BY 1""", {
        'confid': conference.id,
    })

    return {
        'sponsorlevels': [
            {
                'name': lvl.levelname,
                'urlname': lvl.urlname,
                'cost': format_currency(lvl.levelcost),
                'available': lvl.available,
                'maxnumber': lvl.maxnumber,
                'instantbuy': lvl.instantbuy,
                'benefits': [dict(_get_benefit_data(b)) for b in lvl.sponsorshipbenefit_set.all()
                ],
            }
            for lvl in SponsorshipLevel.objects.filter(conference=conference, public=True)
        ],
        'sponsorbenefitsbylevel': [
            {
                'name': b[0],
                'benefits': b[1],
                'countedbenefit': max([int(x) if x.isnumeric() else 2 for x in b[1] if x is not None]) > 1,
            }
            for b in overviewdata
        ]
    }


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


def send_sponsor_manager_simple_email(sponsor, subject, message, attachments=None):
    for manager in sponsor.managers.all():
        send_conference_simple_mail(
            sponsor.conference,
            manager.email,
            subject,
            message,
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


def get_pdf_fields_for_conference(conference, sponsor=None, overrides={}):
    fields = [
        ('static:sponsor', sponsor.name if sponsor else overrides.get('static:sponsor', 'Sponsor company name')),
    ]
    if settings.EU_VAT:
        fields.append(
            ('static:euvat', sponsor.vatnumber if sponsor else overrides.get('static:euvat', 'Sponsor EU VAT number')),
        )

    return fields
