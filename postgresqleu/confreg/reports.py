from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings
from django.contrib import messages

from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet

import csv
import json

from .jinjapdf import render_jinja_badges

from postgresqleu.util.db import exec_to_dict
from postgresqleu.util.db import ensure_conference_timezone
from postgresqleu.countries.models import Country
from .models import ConferenceRegistration, RegistrationType, ConferenceAdditionalOption, ShirtSize
from .models import STATUS_CHOICES
from .reportingforms import QueuePartitionForm
from functools import reduce


class ReportField(object):
    virtualfield = False

    def __init__(self, id, title, default=False):
        self.id = id
        self.title = title
        self.default = default
        if not self.virtualfield:
            self.field = ConferenceRegistration._meta.get_field(id)

    def get_select_name(self):
        return self.id

    def get_value(self, val):
        if type(val) == bool:
            return val and 'Yes' or 'No'
        elif type(val) != str:
            return str(val)
        return val

    def get_orderby_field(self):
        return self.id

    def get_join(self):
        return None


class DerivedReportField(ReportField):
    virtualfield = True

    def __init__(self, id, title, expression, default=False):
        super(DerivedReportField, self).__init__(id, title, default)
        self.expression = expression

    def get_select_name(self):
        return "{} AS {}".format(self.expression, self.id)


class ForeignReportField(ReportField):
    def __init__(self, id, title, remotecol, sort=None, default=False):
        super(ForeignReportField, self).__init__(id, title, default)
        self.sort = sort
        self.remotecol = remotecol

    def get_select_name(self):
        return "{}.{} AS {}".format(
            self.field.remote_field.model._meta.db_table,
            self.remotecol,
            self.id,
        )

    def get_orderby_field(self):
        if self.sort:
            return "{}.{}".format(
                self.field.remote_field.model._meta.db_table,
                self.sort,
            )
        else:
            return "{}.{}".format(
                self.field.remote_field.model._meta.db_table,
                self.remotecol,
            )

    def get_join(self):
        joincols = self.field.get_joining_columns()
        if len(joincols) != 1:
            raise Exception("Wrong number of join columns")

        return "LEFT JOIN {} ON r.{}={}.{}".format(
            self.field.remote_field.model._meta.db_table,
            joincols[0][0],
            self.field.remote_field.model._meta.db_table,
            joincols[0][1],
        )


class AdditionalOptionsReportField(object):
    def __init__(self):
        self.id = 'additionaloptions'
        self.title = 'Additional Options'

    def get_select_name(self):
        return "(\n          SELECT array_agg(name) FROM confreg_conferenceadditionaloption ccao\n          INNER JOIN confreg_conferenceregistration_additionaloptions ccrao ON ccrao.conferenceadditionaloption_id=ccao.id\n          WHERE ccrao.conferenceregistration_id=r.id\n       ) AS additionaloptions"

    def get_value(self, val):
        if val:
            return ",\n".join(val)
        else:
            return ''

    def get_orderby_field(self):
        raise Exception("Can't order by this")

    def get_join(self):
        return None


# Fields that are available in an advanced attendee report
attendee_report_fields = [
    ReportField('lastname', 'Last name', True),
    ReportField('firstname', 'First name', True),
    ReportField('email', 'E-mail', True),
    DerivedReportField('queuepartition', 'Queue partition', "regexp_replace(upper(substring(CASE WHEN conference.queuepartitioning=1 THEN lastname WHEN conference.queuepartitioning=2 THEN firstname END, 1, 1)), '[^A-Z]', 'Other')"),
    ReportField('company', 'Company'),
    ReportField('address', 'Address'),
    ForeignReportField('country', 'Country', remotecol='printable_name'),
    ReportField('phone', 'Phone'),
    ReportField('twittername', 'Twitter'),
    ReportField('nick', 'Nickname'),
    ReportField('dietary', 'Dietary needs'),
    ForeignReportField('shirtsize', 'T-Shirt size', remotecol='shirtsize', sort='shirtsize'),
    ReportField('photoconsent', 'Photo consent'),
    ForeignReportField('regtype', 'Registration type', remotecol='regtype', sort='sortkey'),
    AdditionalOptionsReportField(),
    ReportField('created', 'Registration created'),
    ReportField('payconfirmedat', 'Payment confirmed'),
    ReportField('canceledat', 'Canceled at'),
    DerivedReportField('publictoken', 'Public token', "'AT$' || publictoken || '$AT'"),
    DerivedReportField('idtoken', 'ID token', "'ID$' || idtoken || '$ID'"),
]


_attendee_report_field_map = {f.id: f for f in attendee_report_fields}


class ReportFilter(object):
    booleanoptions = ((1, 'Yes'), (0, 'No'))

    def __init__(self, id, name, queryset=None, querysetcol=None, emptyasnull=True, manytomany=False):
        self.id = id
        self.name = name
        self.queryset = queryset
        self.querysetcol = querysetcol
        self.emptyasnull = emptyasnull
        if self.queryset:
            self.type = 'select'
        else:
            self.type = 'string'
        self.manytomany = manytomany
        self.field = ConferenceRegistration._meta.get_field(id)
        self.db_colname = self.field.get_attname_column()[1]

    def build_SQL(self, flt, blockno):
        val = flt['value']
        if self.queryset:
            # Our input is a list of IDs.
            # Note! For some silly models (hello Country), the id is text :/ So we need
            # to figure that out.
            if self.queryset == self.booleanoptions:
                idlist = [bool(int(v)) for v in val]
            elif isinstance(self.queryset, tuple):
                idlist = [int(v) for v in val]
            else:
                idlist = list(map(self.field.related_model._meta.pk.get_prep_value, val))
            if flt.get('mincount', None) is None:
                return (
                    '{}=ANY(%({}_ids)s)'.format(self.db_colname, self.id),
                    {'{}_ids'.format(self.id): idlist},
                )
            else:
                # We have a minimum count, so we turn this into a subquery this time
                return (
                    '(SELECT count(*) FROM {} {}_{} WHERE {}_{}.{}=r.id AND {}=ANY(%({}_ids_{})s)) >= %({}_mincount_{})s'.format(
                        self.field.m2m_db_table(),      # SELECT FROM
                        self.field.m2m_db_table(),      # SELECT FROM alias
                        blockno,                        # SELECT FROM alias
                        self.field.m2m_db_table(),      # WHERE table alias
                        blockno,                        # WHERE table alias
                        self.field.m2m_column_name(),   # column in binding table
                        self.field.m2m_reverse_name(),  # column where our ids live
                        self.id,             # {}_ids
                        blockno,             # _ids{}
                        self.id,             # {}_mincount
                        blockno,             # _mincount{}
                    ),
                    {
                        '{}_mincount_{}'.format(self.id, blockno): int(flt.get('mincount')),
                        '{}_ids_{}'.format(self.id, blockno): idlist,
                    },
                )
        else:
            if val != '':
                # Limit by value
                # First try to case it to the appropriate format, so we get a formatting error rather than
                # a later runtime error crash if the format is bad.
                fval = self.field.get_prep_value(val[1:])

                if val.startswith('>'):
                    return (
                        "{} > %({})s".format(self.db_colname, self.id),
                        {self.id: val[1:]}
                    )
                elif val.startswith('<'):
                    return (
                        "{} < %({})s".format(self.db_colname, self.id),
                        {self.id: val[1:]}
                    )
                else:
                    return (
                        "{} ILIKE %({})s".format(self.db_colname, self.id),
                        {self.id: '%{}%'.format(val)}
                    )
            else:
                # Just make sure it exists
                if self.emptyasnull:
                    return (
                        "{} IS NOT NULL AND {} != ''".format(self.db_colname, self.db_colname),
                        {}
                    )
                else:
                    return (
                        "{} IS NOT NULL".format(self.db_colname),
                        {}
                    )

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


class ReportQueuePartitionFilter(object):
    id = 'queuepartition'
    name = 'Queue partition'
    type = 'select'

    def __init__(self, conference):
        self.conference = conference

    def build_SQL(self, flt, blockno):
        val = flt['value']
        letters = [k for k in val if k != 'Other']
        other = 'Other' in val

        p = []
        if letters:
            p.append("[{0}]".format(''.join(letters)))
        if other:
            p.append("[^A-Z]")
        r = "^({0})".format('|'.join(p))

        return (
            "r.{} ~* %(qpart_{})s".format(
                (self.conference.queuepartitioning == 1) and 'lastname' or 'firstname',
                blockno),
            {"qpart_{}".format(blockno): r}
        )

    def options(self):
        return [['Other', 'Other']] + [(chr(x), chr(x)) for x in range(ord('A'), ord('Z') + 1)]


# Filter by speaker having at least one session in any of the given states
class ReportSpeakerFilter(object):
    id = 'speakerstate'
    name = 'Speaker with sessions'
    type = 'select'

    def __init__(self, conference):
        self.conference = conference

    def build_SQL(self, flt, blockno):
        val = flt['value']
        return (
            "EXISTS (SELECT 1 FROM confreg_conferencesession conferencesession_{0} INNER JOIN confreg_conferencesession_speaker conferencesession_speaker_{0} ON conferencesession_{0}.id=conferencesession_speaker_{0}.conferencesession_id INNER JOIN confreg_speaker speaker_{0} ON conferencesession_speaker_{0}.speaker_id=speaker_{0}.id WHERE speaker_{0}.user_id=r.attendee_id AND conferencesession_{0}.conference_id=%(conference_id)s AND conferencesession_{0}.status=ANY(%(sessionstatuses_{0})s))".format(blockno),
            {"sessionstatuses_{}".format(blockno): [int(v) for v in val]}
        )

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
        ReportFilter('badgescan', 'Allow badge scanning', ReportFilter.booleanoptions),
        ReportFilter('shareemail', 'Share email with sponsors', ReportFilter.booleanoptions),
        ReportFilter('photoconsent', 'Photo consent', ReportFilter.booleanoptions),
        ReportFilter('payconfirmedat', 'Payment confirmed', emptyasnull=False),
        ReportFilter('canceledat', 'Canceled at', emptyasnull=False),
        ReportFilter('additionaloptions', 'Additional options', ConferenceAdditionalOption.objects.filter(conference=conference), 'name', False, True),
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
    def set_orientation_and_size(self, orientation, pagesize):
        self.orientation = orientation
        self.pagesize = pagesize

    def render(self):
        resp = HttpResponse(content_type='application/pdf')

        registerFont(TTFont('DejaVu Serif', "{}/DejaVuSerif.ttf".format(settings.FONTROOT)))
        pagesize = LETTER if self.pagesize == 'letter' else A4
        if self.orientation != 'portrait':
            pagesize = landscape(pagesize)
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
    pagesize = data.get('pagesize', 'A4')
    borders = data['borders']
    pagebreaks = data['pagebreaks']
    fields = data['fields']
    extracols = [_f for _f in [x.strip() for x in data['additionalcols'].split(',')] if _f]

    # Build the filters. Each filter within a filter group is ANDed together, and then the
    # filter groups are ORed together. And finally, all of this is ANDed with the conference
    # (so we don't get attendees from other conferences)
    def _reduce_Q(x, y):
        return (
            x[0] + [y[0]],
            dict(x[1], **y[1])
        )

    filtermap = attendee_report_filters_map(conference)
    allBlockQs = []
    for blockno, fltblock in enumerate(data['filters']):
        if fltblock:
            try:
                blockQs = reduce(_reduce_Q,
                                 [filtermap[flt['filter']].build_SQL(flt, blockno) for flt in fltblock],
                                 ([], {})
                )
                allBlockQs.append((
                    "(" + "\n      AND ".join(blockQs[0]) + ")",
                    blockQs[1],
                ), )
            except Exception as e:
                if format == 'html':
                    messages.warning(request, "Could not process filter: {}".format(e))
                else:
                    return HttpResponse("Could not process filter: {}".format(e))

    if allBlockQs:
        (allblocks, params) = reduce(_reduce_Q, allBlockQs, ([], {}))
        where = "AND (\n    {}\n)".format(
            "\n OR ".join(allblocks),
        )
    else:
        where = ""
        params = {}

    params.update({
        'conference_id': conference.id,
    })

    ofields = [_attendee_report_field_map[f] for f in (data['orderby1'], data['orderby2'])]
    if format not in ('json', 'badge'):
        # Regular reports, so we control all fields
        rfields = [_attendee_report_field_map[f] for f in fields]

        # Colums to actually select (including expressions)
        cols = [f.get_select_name() for f in rfields]

        # Table to join in to get the required columns
        joins = [j.get_join() for j in rfields if j.get_join()]

        # There could be more joins needed for the order by
        joins.extend([j.get_join() for j in ofields if j.get_join() and j.get_join() not in joins])
        joinstr = "\n".join(joins)
        if joinstr:
            joinstr = "\n" + joinstr

        query = "SELECT r.id,{}\nFROM confreg_conferenceregistration r INNER JOIN confreg_conference conference ON conference.id=r.conference_id{}\nWHERE r.conference_id=%(conference_id)s {}\nORDER BY {}".format(
            ", ".join(cols),
            joinstr,
            where,
            ", ".join([o.get_orderby_field() for o in ofields]),
        )
    else:
        # For json and badge, we have a mostly hardcoded query, but we still get the filter from
        # above.
        # We do this hardcoded because the django ORM can't even begin to understand what we're
        # doing here, and generates a horrible loop of queries.
        query = """SELECT r.id, firstname, lastname, email, company, address, phone, dietary, twittername, nick, badgescan, shareemail,
  country.name AS countryname, country.printable_name AS country,
  s.shirtsize,
  'ID$' || idtoken || '$ID' AS fullidtoken,
  'AT$' || publictoken || '$AT' AS fullpublictoken,
  regexp_replace(upper(substring(CASE WHEN conference.queuepartitioning=1 THEN lastname WHEN conference.queuepartitioning=2 THEN firstname END, 1, 1)), '[^A-Z]', 'Other') AS queuepartition,
  json_build_object('regtype', rt.regtype, 'specialtype', rt.specialtype,
    'days', (SELECT array_agg(day) FROM confreg_registrationday rd INNER JOIN confreg_registrationtype_days rtd ON rtd.registrationday_id=rd.id WHERE rtd.registrationtype_id=rt.id),
  'regclass', json_build_object('regclass', rc.regclass, 'badgecolor', rc.badgecolor, 'badgeforegroundcolor', rc.badgeforegroundcolor,
        'bgcolortuplestr', CASE WHEN badgecolor!='' THEN ('x'||substring(badgecolor, 2, 2))::bit(8)::int || ',' || ('x'||substring(badgecolor, 4, 2))::bit(8)::int || ',' || ('x'||substring(badgecolor, 6, 2))::bit(8)::int END,
        'fgcolortuplestr', CASE WHEN badgeforegroundcolor!='' THEN ('x'||substring(badgeforegroundcolor, 2, 2))::bit(8)::int || ',' || ('x'||substring(badgeforegroundcolor, 4, 2))::bit(8)::int || ',' || ('x'||substring(badgeforegroundcolor, 6, 2))::bit(8)::int END
        )
  ) AS regtype,
  COALESCE(json_agg(json_build_object('id', ao.id, 'name', ao.name)) FILTER (WHERE ao.id IS NOT NULL), '[]') AS additionaloptions
FROM confreg_conferenceregistration r
INNER JOIN confreg_conference conference ON conference.id=r.conference_id
INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
INNER JOIN confreg_registrationclass rc ON rc.id=rt.regclass_id
LEFT JOIN confreg_conferenceregistration_additionaloptions crao ON crao.conferenceregistration_id=r.id
LEFT JOIN confreg_conferenceadditionaloption ao ON crao.conferenceadditionaloption_id=ao.id
LEFT JOIN country ON country.iso=r.country_id
LEFT JOIN confreg_shirtsize s ON s.id=r.shirtsize_id
WHERE r.conference_id=%(conference_id)s {}
GROUP BY r.id, conference.id, rt.id, rc.id, country.iso, s.id
ORDER BY {}""".format(where, ", ".join([o.get_orderby_field() for o in ofields]))

    with ensure_conference_timezone(conference):
        result = exec_to_dict(query, params)

    if format == 'html':
        writer = ReportWriterHtml(request, conference, title, borders)
    elif format == 'pdf':
        writer = ReportWriterPdf(request, conference, title, borders)
        writer.set_orientation_and_size(orientation, pagesize)
    elif format == 'csv':
        writer = ReportWriterCsv(request, conference, title, borders)
    elif format == 'json':
        resp = HttpResponse(content_type='application/json')
        json.dump(result, resp, indent=2)
        return resp
    elif format == 'badge':
        try:
            resp = HttpResponse(content_type='application/pdf')
            render_jinja_badges(conference, settings.FONTROOT, result, resp, borders, pagebreaks, orientation, pagesize)
            return resp
        except Exception as e:
            return HttpResponse("Exception occured: %s" % e, content_type='text/plain')
    else:
        raise Exception("Unknown format")

    allheaders = [_attendee_report_field_map[f].title for f in fields]
    if len(extracols):
        allheaders.extend(extracols)
    writer.set_headers(allheaders)

    for r in result:
        row = [_attendee_report_field_map[f].get_value(r[f]) for f in fields]
        row.extend([[]] * len(extracols))
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
                  AND r.canceledat IS NULL
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
                         canceledat IS NULL AND
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
WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND canceledat IS NULL
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
WHERE payconfirmedat IS NOT NULL AND canceledat IS NULL AND conference_id=%(confid)s
GROUP BY printable_name
ORDER BY 2 DESC""",

    'regdays': """WITH t AS (
   SELECT r.id, rd.day
   FROM confreg_conferenceregistration r
   INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
   INNER JOIN confreg_registrationtype_days rtd ON rtd.registrationtype_id=rt.id
   INNER JOIN confreg_registrationday rd ON rd.id=rtd.registrationday_id
   WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL
 UNION
   SELECT r.id, rd.day
   FROM confreg_conferenceregistration r
   INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id
   INNER JOIN confreg_conferenceadditionaloption ao ON ao.id=rao.conferenceadditionaloption_id
   INNER JOIN confreg_conferenceadditionaloption_additionaldays aoad ON aoad.conferenceadditionaloption_id=ao.id
   INNER JOIN confreg_registrationday rd ON rd.id=aoad.registrationday_id
   WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL
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

    'attendeesnotcheckedin': """SELECT
   lastname AS "Last name",
   firstname AS "First name",
   regtype AS "Registration type",
   COALESCE(c.printable_name, $$Unspecified$$) AS "Country"
FROM confreg_conferenceregistration r
INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
LEFT JOIN country c ON c.iso=r.country_id
WHERE r.conference_id=%(confid)s AND
      payconfirmedat IS NOT NULL AND
      canceledat IS NULL AND
      checkedinat IS NULL
ORDER BY lastname, firstname""",

    'speakersnotcheckedin': """SELECT
   lastname AS "Last name",
   firstname AS "First name",
   r.email AS "E-mail",
   title AS "Title",
   COALESCE(track.trackname, '<No track>') AS "Track name"
FROM confreg_speaker spk
INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id
INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id
INNER JOIN confreg_conferenceregistration r ON r.attendee_id=spk.user_id
INNER JOIN confreg_status_strings stat ON stat.id=s.status
LEFT JOIN confreg_track track ON track.id=s.track_id
WHERE s.conference_id=%(confid)s AND s.status=1
AND r.conference_id=%(confid)s
AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL
AND r.checkedinat IS NULL
ORDER BY lastname, firstname""",
}
