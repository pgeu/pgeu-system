from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django import forms

from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet

import csv
import json

from .jinjapdf import render_jinja_badges

from postgresqleu.countries.models import Country
from .models import ConferenceRegistration, RegistrationType, ConferenceAdditionalOption, ShirtSize
from .models import STATUS_CHOICES
from .reportingforms import QueuePartitionForm
from functools import reduce

# Fields that are available in an advanced attendee report
# (id, field title, default, field_user_for_order_by)
attendee_report_fields = [
    ('lastname', 'Last name', True, None),
    ('firstname', 'First name', True, None),
    ('queuepartition', 'Queue partition', False, None),
    ('email', 'E-mail', True, None),
    ('company', 'Company', False, None),
    ('address', 'Address', False, None),
    ('country', 'Country', False, None),
    ('phone', 'Phone', False, None),
    ('twittername', 'Twitter', False, None),
    ('nick', 'Nickname', False, None),
    ('dietary', 'Dietary needs', False, None),
    ('shirtsize.shirtsize', 'T-Shirt size', False, 'shirtsize__shirtsize'),
    ('photoconsent', 'Photo consent', False, None),
    ('regtype.regtype', 'Registration type', False, 'regtype__sortkey'),
    ('additionaloptionlist', 'Additional options', False, 'id'),
    ('created', 'Registration created', False, None),
    ('payconfirmedat', 'Payment confirmed', False, None),
    ('fullpublictoken', 'Public token', False, None),
    ('fullidtoken', 'ID token', False, None),
]

_attendee_report_field_map = dict([(a, (b, c, d)) for a, b, c, d in attendee_report_fields])


class ReportFilter(object):
    def __init__(self, id, name, queryset=None, querysetcol=None, emptyasnull=True):
        self.id = id
        self.name = name
        self.queryset = queryset
        self.querysetcol = querysetcol
        self.emptyasnull = emptyasnull
        if self.queryset:
            self.type = 'select'
        else:
            self.type = 'string'

    def build_Q(self, val):
        if self.queryset and not isinstance(self.queryset, tuple) and not isinstance(self.queryset, list):
            # Our input is a list of IDs. Return registrations that has
            # *any* of the given id's. But we need to make sure that
            # django doesn't evaluate it as a subselect.
            return Q(**{"%s__pk__in" % self.id: val})
        elif self.queryset:
            # Our input is a list of IDs, but they should be looked up
            # in a set of tuples rather than as foreign keys.
            return Q(**{"%s__in" % self.id: val})
        else:
            if val != '':
                # Limit by value
                if val.startswith('>'):
                    return Q(**{"%s__gt" % self.id: val[1:]})
                elif val.startswith('<'):
                    return Q(**{"%s__lt" % self.id: val[1:]})
                else:
                    return Q(**{"%s__icontains" % self.id: val})
            else:
                # Just make sure it exists
                if self.emptyasnull:
                    return Q(**{"%s__isnull" % self.id: False, "%s__gt" % self.id: ''})
                else:
                    return Q(**{"%s__isnull" % self.id: False})

    def options(self):
        if isinstance(self.queryset, tuple) or isinstance(self.queryset, list):
            return self.queryset
        else:
            def _get_value(obj):
                if self.querysetcol:
                    return getattr(obj, self.querysetcol)
                else:
                    return str(obj)
            return [(o.pk, _get_value(o)) for o in self.queryset.all()]


class ReportQueuePartitionFilter(ReportFilter):
    def __init__(self, conference):
        self.conference = conference
        super(ReportQueuePartitionFilter, self).__init__(
            'queuepartition',
            'Queue Partition',
            [['Other', 'Other']] + [(chr(x), chr(x)) for x in range(ord('A'), ord('Z') + 1)]
        )

    def build_Q(self, val):
        letters = [k for k in val if k != 'Other']
        other = 'Other' in val

        p = []
        if letters:
            p.append("[{0}]".format(''.join(letters)))
        if other:
            p.append("[^A-Z]")
        r = "^({0})".format('|'.join(p))

        if self.conference.queuepartitioning == 1:
            return Q(lastname__iregex=r)
        else:
            return Q(firstname__iregex=r)


# Filter by speaker state is more complex than the default filter can handle,
# so it needs a special implementation.
class ReportSpeakerFilter(object):
    id = 'speakerstate'
    name = 'Speaker with sessions'
    type = 'select'

    def __init__(self, conference):
        self.conference = conference

    def build_Q(self, val):
        return Q(attendee__speaker__conferencesession__conference=self.conference,
                 attendee__speaker__conferencesession__status__in=val)

    def options(self):
        return STATUS_CHOICES


def attendee_report_filters(conference):
    return [
        ReportFilter('regtype', 'Registration type', RegistrationType.objects.filter(conference=conference), 'regtype'),
        ReportFilter('lastname', 'Last name'),
        ReportFilter('firstname', 'First name'),
        ReportQueuePartitionFilter(conference),
        ReportFilter('country', 'Country', Country.objects.all()),
        ReportFilter('company', 'Company'),
        ReportFilter('phone', 'Phone'),
        ReportFilter('twittername', 'Twitter'),
        ReportFilter('nick', 'Nickname'),
        ReportFilter('dietary', 'Dietary needs'),
        ReportFilter('badgescan', 'Allow badge scanning', ((1, 'Yes'), (0, 'No'))),
        ReportFilter('shareemail', 'Share email with sponsors', ((1, 'Yes'), (0, 'No'))),
        ReportFilter('photoconsent', 'Photo consent', ((1, 'Yes'), (0, 'No'))),
        ReportFilter('payconfirmedat', 'Payment confirmed', emptyasnull=False),
        ReportFilter('additionaloptions', 'Additional options', ConferenceAdditionalOption.objects.filter(conference=conference), 'name', False),
        ReportFilter('shirtsize', 'T-Shirt size', ShirtSize.objects.all()),
        ReportSpeakerFilter(conference),
    ]


def attendee_report_filters_map(conference):
    return {r.id: r for r in attendee_report_filters(conference)}


class ReportWriterBase(object):
    def __init__(self, request, conference, title, borders):
        self.request = request
        self.conference = conference
        self.rows = []
        self.title = title
        self.borders = borders

    def set_headers(self, headers):
        self.headers = headers

    def add_row(self, row):
        self.rows.append(row)


class ReportWriterHtml(ReportWriterBase):
    def render(self):
        return render(self.request, 'confreg/simple_report.html', {
            'conference': self.conference,
            'columns': self.headers,
            'data': self.rows,
            'helplink': 'reports',
            'breadcrumbs': (('/events/admin/{0}/reports/'.format(self.conference.urlname), 'Attendee reports'), ),
            'backurl': '/events/admin/{0}/reports/'.format(self.conference.urlname),
            'backwhat': 'attendee reports',
        })


class ReportWriterCsv(ReportWriterBase):
    def render(self):
        resp = HttpResponse(content_type='text/plain; charset=utf-8')
        c = csv.writer(resp, delimiter=';')
        for r in self.rows:
            c.writerow(r)

        return resp


class ReportWriterPdf(ReportWriterBase):
    def set_orientation(self, orientation):
        self.orientation = orientation

    def render(self):
        resp = HttpResponse(content_type='application/pdf')

        registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
        pagesize = self.orientation == 'portrait' and A4 or landscape(A4)
        doc = SimpleDocTemplate(resp, pagesize=pagesize)

        story = []

        story.append(Paragraph(self.title, getSampleStyleSheet()['title']))

        tbldata = [self.headers]
        tbldata.extend(self.rows)
        t = Table(tbldata, splitByRow=1, repeatRows=1)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), "DejaVu Serif"),
            ]
        if self.borders:
            style.extend([
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ])
        t.setStyle(TableStyle(style))
        story.append(t)

        doc.build(story)

        return resp


def build_attendee_report(request, conference, data):
    title = data['title']
    format = data['format']
    orientation = data['orientation']
    borders = data['borders']
    pagebreaks = data['pagebreaks']
    fields = data['fields']
    extracols = [_f for _f in [x.strip() for x in data['additionalcols'].split(',')] if _f]

    # Build the filters. Each filter within a filter group is ANDed together, and then the
    # filter groups are ORed together. And finally, all of this is ANDed with the conference
    # (so we don't get attendees from other conferences)
    filtermap = attendee_report_filters_map(conference)
    allBlockQs = []
    for fltblock in data['filters']:
        blockQs = []
        for flt in fltblock:
            f = filtermap[flt['filter']]
            blockQs.append(f.build_Q(flt['value']))
        allBlockQs.append(reduce(lambda x, y: x & y, blockQs))
    q = Q(conference=conference) & reduce(lambda x, y: x | y, allBlockQs)

    # Figure out our order by
    orderby = [_attendee_report_field_map[x][2] and _attendee_report_field_map[x][2] or x for x in [data['orderby1'], data['orderby2']]]

    # Run the query!
    result = ConferenceRegistration.objects.select_related('shirtsize', 'regtype', 'country', 'conference').filter(q).distinct().order_by(*orderby)

    if format == 'html':
        writer = ReportWriterHtml(request, conference, title, borders)
    elif format == 'pdf':
        writer = ReportWriterPdf(request, conference, title, borders)
        writer.set_orientation(orientation)
    elif format == 'csv':
        writer = ReportWriterCsv(request, conference, title, borders)
    elif format == 'json':
        # Don't want to use normal renderer here, since we need to pass
        # the filtered full objects into the builder (because it needs to
        # be the same data as the badges get)
        resp = HttpResponse(content_type='application/json')
        json.dump([r.safe_export() for r in result], resp, indent=2)
        return resp
    elif format == 'badge':
        # Can't use a normal renderer here, since we need to actually
        # pass the full objects into the badge builder.
        try:
            resp = HttpResponse(content_type='application/pdf')
            render_jinja_badges(conference, result, resp, borders, pagebreaks)
            return resp
        except Exception as e:
            return HttpResponse("Exception occured: %s" % e, content_type='text/plain')
    else:
        raise Exception("Unknown format")

    allheaders = [_attendee_report_field_map[f][0] for f in fields]
    if len(extracols):
        allheaders.extend(extracols)
    writer.set_headers(allheaders)

    for r in result:
        row = []
        for f in fields:
            # Recursively step into other models if necessary
            o = [r]
            o.extend(f.split('.'))
            try:
                t = reduce(getattr, o)
                if type(t) == bool:
                    row.append(t and 'Yes' or 'No')
                else:
                    row.append(str(t))
            except AttributeError:
                # NULL in a field, typically
                row.append('')
        if extracols:
            for x in extracols:
                row.append('')
        writer.add_row(row)

    return writer.render()


#
# Simple conference reports - basically, just queries and sometimes mapped with a form
#
simple_reports = {
    'unregspeaker': """SELECT DISTINCT
   fullname AS "Name",
   u.email AS "E-mail"
FROM confreg_speaker spk
INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id
INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id
INNER JOIN auth_user u ON u.id=spk.user_id
WHERE s.conference_id=%(confid)s AND
      s.status=1 AND
      NOT EXISTS (SELECT * FROM confreg_conferenceregistration r
                  WHERE r.conference_id=%(confid)s
                  AND r.payconfirmedat IS NOT NULL
                  AND r.attendee_id=spk.user_id)
ORDER BY fullname""",
    'unregstaff': """SELECT
   last_name,
   first_name,
   email
FROM auth_user u
INNER JOIN confreg_conference_staff s ON s.user_id=u.id
WHERE s.conference_id=%(confid)s AND
      u.id NOT IN (SELECT attendee_id FROM confreg_conferenceregistration r
                   WHERE r.conference_id=%(confid)s AND
                         payconfirmedat IS NOT NULL AND
                         attendee_id IS NOT NULL
                  )
ORDER BY last_name, first_name""",

    'unconfirmspeaker': """SELECT
   fullname AS "Name",
   u.email AS "E-mail",
   title AS "Title",
   COALESCE(track.trackname, '<No track>') AS "Track name",
   stat.statustext AS "Session status"
FROM confreg_speaker spk
INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id
INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id
INNER JOIN auth_user u ON u.id=spk.user_id
INNER JOIN confreg_status_strings stat ON stat.id=s.status
LEFT JOIN confreg_track track ON track.id=s.track_id
WHERE s.conference_id=%(confid)s AND s.status IN (3,5)
ORDER BY fullname""",

    'sessionstatus': """SELECT
   ss.id AS _id,
   statustext AS "Status",
   count(*) AS "Count",
   NULL as "Sum"
FROM confreg_conferencesession s
INNER JOIN confreg_status_strings ss ON ss.id=s.status
WHERE conference_id=%(confid)s
GROUP BY ss.id

UNION ALL

SELECT
   10000,
    statusgroup,
    NULL,
    count(*)
FROM confreg_conferencesession s
INNER JOIN confreg_status_strings ss ON ss.id=s.status
WHERE conference_id=%(confid)s AND statusgroup IS NOT NULL
GROUP BY statusgroup

ORDER BY 1""",

    'tshirtsizes': """SELECT
   shirtsize AS "Size",
   count(*) AS "Num",
   round(count(*)*100/sum(count(*)) over ()) AS "Percent"
FROM confreg_conferenceregistration r
INNER JOIN confreg_shirtsize s ON s.id=r.shirtsize_id
WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL
GROUP BY shirtsize_id, shirtsize
ORDER BY shirtsize_id""",
    'tshirtsizes__anon': """SELECT
   shirtsize AS "Size",
   num as "Num",
   round(num*100/sum(num) over (), 0) AS "Percent"
FROM confreg_aggregatedtshirtsizes t
INNER JOIN confreg_shirtsize s ON s.id=t.size_id
WHERE t.conference_id=%(confid)s
ORDER BY size_id""",
    'countries': """SELECT
   COALESCE(printable_name, $$Unspecified$$) AS "Country",
   count(*) AS "Registrations"
FROM confreg_conferenceregistration
LEFT JOIN country ON country.iso=country_id
WHERE payconfirmedat IS NOT NULL AND conference_id=%(confid)s
GROUP BY printable_name
ORDER BY 2 DESC""",

    'regdays': """WITH t AS (
   SELECT r.id, rd.day
   FROM confreg_conferenceregistration r
   INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
   INNER JOIN confreg_registrationtype_days rtd ON rtd.registrationtype_id=rt.id
   INNER JOIN confreg_registrationday rd ON rd.id=rtd.registrationday_id
   WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL
 UNION
   SELECT r.id, rd.day
   FROM confreg_conferenceregistration r
   INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id
   INNER JOIN confreg_conferenceadditionaloption ao ON ao.id=rao.conferenceadditionaloption_id
   INNER JOIN confreg_conferenceadditionaloption_additionaldays aoad ON aoad.conferenceadditionaloption_id=ao.id
   INNER JOIN confreg_registrationday rd ON rd.id=aoad.registrationday_id
   WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL
)
SELECT
   day,count(*)
FROM t
GROUP BY day
ORDER BY day""",

    'sessnoroom': """SELECT
   title AS \"Title\",
   trackname AS \"Track\",
   starttime || ' - ' || endtime AS \"Timeslot\"
FROM confreg_conferencesession s
LEFT JOIN confreg_track t ON t.id=s.track_id
WHERE s.conference_id=%(confid)s AND status=1 AND room_id IS NULL AND NOT cross_schedule""",
    'sessnotrack': """SELECT
   title AS \"Title\",
   roomname AS \"Room\",
   starttime || ' - ' || endtime AS \"Timeslot\"
FROM confreg_conferencesession s
LEFT JOIN confreg_room r ON r.id=s.room_id
WHERE s.conference_id=%(confid)s AND status=1 AND track_id IS NULL""",
    'sessoverlaproom': """SELECT
   roomname AS \"Room\",
   title AS \"Title\",
   starttime || ' - ' || endtime AS \"Timeslot\"
FROM confreg_conferencesession s
INNER JOIN confreg_room r ON r.id=s.room_id
WHERE s.conference_id=%(confid)s AND
      r.conference_id=%(confid)s AND
      status=1 AND
      EXISTS (SELECT 1 FROM confreg_conferencesession s2
              WHERE s2.conference_id=%(confid)s AND
                    s2.status=1 AND
                    s2.room_id=s.room_id AND
                    s.id != s2.id AND
                    tstzrange(s.starttime, s.endtime) && tstzrange(s2.starttime, s2.endtime)
      )
ORDER BY 1,3""",

    'queuepartitions': QueuePartitionForm,

    'notcheckedin': """SELECT
   lastname AS "Last name",
   firstname AS "First name",
   regtype AS "Registration type",
   COALESCE(c.printable_name, $$Unspecified$$) AS "Country"
FROM confreg_conferenceregistration r
INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
LEFT JOIN country c ON c.iso=r.country_id
WHERE r.conference_id=%(confid)s AND
      payconfirmedat IS NOT NULL AND
      checkedinat IS NULL
ORDER BY lastname, firstname""",
}
