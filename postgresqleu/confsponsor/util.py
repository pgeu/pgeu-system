from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.template.defaultfilters import slugify

from postgresqleu.util.db import exec_to_list
from postgresqleu.util.currency import format_currency
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.confreg.util import send_conference_mail, send_conference_simple_mail
from postgresqleu.confsponsor.models import SponsorMail
from postgresqleu.confsponsor.models import Sponsor
from postgresqleu.confsponsor.models import SponsorshipLevel
from postgresqleu.confsponsor.models import SponsorClaimedBenefit
from postgresqleu.confsponsor.benefits import get_benefit_class
from postgresqleu.confsponsor.benefitclasses import all_benefits


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
ORDER BY max(b.sortkey), a.overview_name""", {
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
                'instantbuy': lvl.contractlevel == 1 or (lvl.contractlevel == 0 and cost > 0),  # legacy
                'contractlevel': lvl.contractlevel_name,
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


def sponsorclaimsdata(conference):
    return {
        'sponsors': {
            'bylevel': [
                {
                    'name': lvl.levelname,
                    # We return sponsors including signup and confirmation time here so they can easily
                    # be (re)sorted if needed.
                    'sponsors': [
                        {
                            'name': s.displayname,
                            'slugname': slugify(s.displayname),
                            'confirmedat': s.confirmedat,
                            'signedupat': s.signupat
                        } for s in lvl.sponsor_set.filter(confirmed=True).order_by('signupat')
                    ],
                } for lvl in SponsorshipLevel.objects.filter(conference=conference)],
            'sponsors': {
                s.displayname: {
                    'name': s.displayname,
                    'slugname': slugify(s.displayname),
                    'url': s.url,
                    'social': s.social,
                    'level': s.level.levelname,
                    'signedupat': s.signupat,
                    'confirmedat': s.confirmedat,
                    'benefits': [
                        {
                            'claimid': b.id,
                            'name': b.benefit.benefitname,
                            'confirmed': b.confirmed,
                            'class': all_benefits[b.benefit.benefit_class]['class'],
                            'claim': get_benefit_class(b.benefit.benefit_class)(s.level, b.benefit.class_parameters).get_claimdata(b),
                        } for b in s.sponsorclaimedbenefit_set.select_related('benefit').filter(declined=False, benefit__include_in_data=True).order_by('id')
                    ]
                } for s in Sponsor.objects.select_related('level').filter(conference=conference, confirmed=True)}
        }
    }


def sponsorclaimsfile(conference, claimid):
    b = get_object_or_404(
        SponsorClaimedBenefit.objects.select_related('benefit', 'sponsor').
        only('id', 'benefit__benefit_class', 'benefit__class_parameters', 'sponsor__id'),
        sponsor__conference=conference, sponsor__confirmed=True, pk=claimid, declined=False,
    )

    return get_benefit_class(b.benefit.benefit_class)(b.sponsor.level, b.benefit.class_parameters).get_claimfile(b)


def send_conference_sponsor_notification(conference, subject, message):
    if conference.sponsoraddr:
        send_simple_mail(conference.sponsoraddr,
                         conference.sponsoraddr,
                         subject,
                         message,
                         sendername=conference.conferencename)


def send_sponsor_manager_email(sponsor, subject, template, context, attachments=None, sendat=None):
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
            receivername='{0} {1}'.format(manager.first_name, manager.last_name),
            sendat=sendat,
        )


def send_sponsor_manager_simple_email(sponsor, subject, message, attachments=None, sendat=None):
    for manager in sponsor.managers.all():
        send_conference_simple_mail(
            sponsor.conference,
            manager.email,
            subject,
            message,
            attachments=attachments,
            sender=sponsor.conference.sponsoraddr,
            sendername=sponsor.conference.conferencename,
            receivername='{0} {1}'.format(manager.first_name, manager.last_name),
            sendat=None,
        )


def get_mails_for_sponsor(sponsor, future=False):
    return SponsorMail.objects.filter(
        Q(conference=sponsor.conference),
        Q(levels=sponsor.level) | Q(sponsors=sponsor),
        sent=not future,
    )


def get_pdf_fields_for_conference(conference, sponsor=None, overrides={}):
    fields = [
        ('static:sponsor', sponsor.name if sponsor else overrides.get('static:sponsor', 'Sponsor company name')),
    ]
    if settings.EU_VAT:
        fields.append(
            ('static:euvat', sponsor.vatnumber if sponsor else overrides.get('static:euvat', 'Sponsor EU VAT number')),
        )
    if sponsor and sponsor.level.contractlevel == 1 and not sponsor.explicitcontract:
        # Only add clickthrough contract fields if it's a clickthrough level (or a preview, with no sponsor yet)
        fields.extend([
            ('static:clickthrough', overrides.get('static:clickthrough', 'Click-through agreement')),
            ('static:clickthroughdate', str(sponsor.signupat.date()) if sponsor else overrides.get('static:clickthroughdate', 'Click-through date')),
        ])

    return fields
