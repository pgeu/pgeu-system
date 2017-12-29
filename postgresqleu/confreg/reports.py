from django.db.models import Q
from django.http import HttpResponse
from django import forms

from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet

import csv
import json

from jinjabadge import render_jinja_badges

from postgresqleu.countries.models import Country
from models import ConferenceRegistration, RegistrationType, ConferenceAdditionalOption, ShirtSize

# Fields that are available in an advanced attendee report
# (id, field title, default, field_user_for_order_by)
attendee_report_fields = [
		('lastname', 'Last name', True, None),
		('firstname', 'First name', True, None),
		('email', 'E-mail', True, None),
		('company', 'Company', False, None),
		('address', 'Address', False, None),
		('country', 'Country', False, None),
		('phone', 'Phone', False, None),
		('twittername', 'Twitter', False, None),
		('nick', 'Nickname', False, None),
		('dietary', 'Dietary needs', False, None),
		('shirtsize.shirtsize', 'T-Shirt size', False, 'shirtsize__shirtsize'),
		('regtype.regtype', 'Registration type', False, 'regtype__sortkey'),
		('additionaloptionlist', 'Additional options', False, 'id'),
		('created', 'Registration created', False, None),
		('payconfirmedat', 'Payment confirmed', False, None),
]

_attendee_report_field_map = dict([(a,(b,c,d)) for a,b,c,d in attendee_report_fields])

class ReportFilter(object):
	def __init__(self, id, name, queryset=None, querysetcol=None, emptyasnull=True):
		self.id = id
		self.name = name
		self.queryset = queryset
		self.querysetcol = querysetcol
		self.emptyasnull = emptyasnull

	def build_Q(self, POST):
		if self.queryset:
			# Our input is a list of IDs. Return registrations that has
			# *any* of the given id's. But we need to make sure that
			# django doesn't evaluate it as a subselect.
			val = POST.getlist("adv_%s" % self.id, None)
			return Q(**{"%s__pk__in" % self.id: val})
		else:
			if POST.has_key('adv_%s_filter' % self.id) and POST['adv_%s_filter' % self.id]:
				# Limit by value
				v = POST['adv_%s_filter' % self.id]
				if v.startswith('>'):
					return Q(**{"%s__gt" % self.id: v[1:]})
				elif v.startswith('<'):
					return Q(**{"%s__lt" % self.id: v[1:]})
				else:
					return Q(**{"%s__icontains" % self.id: v})
			else:
				# Just make sure it exists
				if self.emptyasnull:
					return Q(**{"%s__isnull" % self.id:False, "%s__gt" % self.id: ''})
				else:
					return Q(**{"%s__isnull" % self.id:False})

	@property
	def html(self):
		return """<input type="checkbox" class="adv_filter_check" name="adv_%s_on">%s%s""" % (
			self.id,
			self.name,
			self._widgetstring(),
		)

	def _widgetstring(self):
		if self.queryset:
			querysetcol = self.querysetcol

			# Wrapper class that will return our custom column
			class MultipleChoiceWrapper(forms.ModelMultipleChoiceField):
				def label_from_instance(self, obj):
					if querysetcol:
						return getattr(obj, querysetcol)
					else:
						return super(MultipleChoiceWrapper, self).label_from_instance(obj)

			field = MultipleChoiceWrapper(queryset=self.queryset)
			return "<blockquote>%s</blockquote><br/>" % (field.widget.render("adv_%s" % self.id, None), )
		else:
			return '<input type="text" class="adv_filter_box" name="adv_%s_filter"><br/>' % self.id

def attendee_report_filters(conference):
	yield ReportFilter('regtype', 'Registration type', RegistrationType.objects.filter(conference=conference), 'regtype')
	yield ReportFilter('lastname', 'Last name')
	yield ReportFilter('firstname', 'First name')
	yield ReportFilter('country', 'Country', Country.objects.all())
	yield ReportFilter('company', 'Company')
	yield ReportFilter('phone', 'Phone')
	yield ReportFilter('twittername', 'Twitter')
	yield ReportFilter('nick', 'Nickname')
	yield ReportFilter('dietary', 'Dietary needs')
	yield ReportFilter('shareemail', 'Share email with sponsors')
	yield ReportFilter('payconfirmedat', 'Payment confirmed', emptyasnull=False)
	yield ReportFilter('additionaloptions', 'Additional options', ConferenceAdditionalOption.objects.filter(conference=conference), 'name')
	yield ReportFilter('shirtsize', 'T-Shirt size', ShirtSize.objects.all())


class ReportWriterBase(object):
	def __init__(self, title, borders):
		self.rows = []
		self.title = title
		self.borders = borders

	def set_headers(self, headers):
		self.headers = headers

	def add_row(self, row):
		self.rows.append(row)

class ReportWriterHtml(ReportWriterBase):
	def render(self):
		resp = HttpResponse()
		if self.title:
			resp.write("<h1>%s</h1>" % self.title)
		resp.write('<table border="%s" cellspacing="0" cellpadding="1"><tr><th>%s</th></tr>' % (self.borders and 1 or 0, "</th><th>".join(self.headers)))
		for r in self.rows:
			resp.write("<tr><td>%s</td></tr>\n" % "</td><td>".join(r))
		resp.write("</table>\n")

		return resp

class ReportWriterCsv(ReportWriterBase):
	def render(self):
		resp = HttpResponse(content_type='text/plain; charset=utf-8')
		c = csv.writer(resp, delimiter=';')
		for r in self.rows:
			c.writerow([x.encode('utf-8') for x in r])

		return resp

class ReportWriterPdf(ReportWriterBase):
	def set_orientation(self, orientation):
		self.orientation = orientation

	def render(self):
		resp = HttpResponse(content_type='application/pdf')

		registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
		pagesize = self.orientation=='portrait' and A4 or landscape(A4)
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
			('GRID', (0,0), (-1, -1), 1, colors.black),
			('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
			])
		t.setStyle(TableStyle(style))
		story.append(t)

		doc.build(story)

		return resp

def build_attendee_report(conference, POST):
	title = POST['title']
	format = POST['format']
	orientation = POST['orientation']
	borders = POST.has_key('border')
	fields = POST.getlist('fields')
	extracols = filter(None, map(lambda x: x.strip(), POST['additionalcols'].split(',')))

	# Build the filters
	q = Q(conference=conference)
	for f in attendee_report_filters(conference):
		if POST.has_key("adv_%s_on" % f.id):
			# This filter is checked
			q = q & f.build_Q(POST)

	# Figure out our order by
	orderby = map(lambda x: _attendee_report_field_map[x][2] and _attendee_report_field_map[x][2] or x, [POST['orderby1'],POST['orderby2']])

	# Run the query!
	result = ConferenceRegistration.objects.select_related('shirtsize', 'regtype', 'country', 'conference').filter(q).distinct().order_by(*orderby)

	if format=='html':
		writer = ReportWriterHtml(title, borders)
	elif format=='pdf':
		writer = ReportWriterPdf(title, borders)
		writer.set_orientation(orientation)
	elif format=='csv':
		writer = ReportWriterCsv(title, borders)
	elif format=='json':
		# Don't want to use normal renderer here, since we need to pass
		# the filtered full objects into the builder (because it needs to
		# be the same data as the badges get)
		resp = HttpResponse(content_type='application/json')
		json.dump([r.safe_export() for r in result], resp, indent=2)
		return resp
	elif format=='badge':
		# Can't use a normal renderer here, since we need to actually
		# pass the full objects into the badge builder.
		try:
			resp = HttpResponse(content_type='application/pdf')
			render_jinja_badges(conference, result, resp, borders)
			return resp
		except Exception, e:
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
				row.append(unicode(reduce(getattr, o)))
			except AttributeError:
				# NULL in a field, typically
				row.append('')
		if extracols:
			for x in extracols:
				row.append('')
		writer.add_row(row)

	return writer.render()


#
# Simple conference reports - basically, just queries
#
simple_reports = {
	'unregspeaker': 'SELECT DISTINCT fullname AS "Name", u.email AS "E-mail" FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id INNER JOIN auth_user u ON u.id=spk.user_id WHERE s.conference_id=%(confid)s AND s.status=1 AND NOT EXISTS (SELECT * FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.attendee_id=spk.user_id) ORDER BY fullname',
	'unregstaff': 'SELECT last_name, first_name, email FROM auth_user u INNER JOIN confreg_conference_staff s ON s.user_id=u.id WHERE s.conference_id=%(confid)s AND u.id NOT IN (SELECT attendee_id FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL) ORDER BY last_name, first_name',
	'unconfirmspeaker': 'SELECT fullname AS "Name", u.email AS "E-mail", title AS "Title" FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id INNER JOIN auth_user u ON u.id=spk.user_id WHERE s.conference_id=%(confid)s AND s.status=3 ORDER BY fullname',
	'sessionstatus': 'SELECT ss.id AS _id, statustext AS "Status",count(*) AS "Count", NULL as "Sum" FROM confreg_conferencesession s INNER JOIN confreg_status_strings ss ON ss.id=s.status WHERE conference_id=%(confid)s GROUP BY ss.id UNION ALL SELECT 10000, statusgroup, NULL, count(*) FROM confreg_conferencesession s INNER JOIN confreg_status_strings ss ON ss.id=s.status WHERE conference_id=%(confid)s AND statusgroup IS NOT NULL GROUP BY statusgroup ORDER BY 1',
	'tshirtsizes': 'SELECT shirtsize AS "Size", count(*) AS "Num", round(count(*)*100/sum(count(*)) over ()) AS "Percent" FROM confreg_conferenceregistration r INNER JOIN confreg_shirtsize s ON s.id=r.shirtsize_id WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL GROUP BY shirtsize_id, shirtsize ORDER BY shirtsize_id',
	'countries': 'SELECT printable_name AS "Country", count(*) AS "Registrations" FROM confreg_conferenceregistration INNER JOIN country ON country.iso=country_id WHERE payconfirmedat IS NOT NULL AND conference_id=%(confid)s GROUP BY printable_name ORDER BY 2 DESC',
	'regdays': 'SELECT day,count(*) FROM confreg_registrationday d INNER JOIN confreg_registrationtype_days rd ON rd.registrationday_id=d.id INNER JOIN confreg_registrationtype rt ON rt.id=rd.registrationtype_id INNER JOIN confreg_conferenceregistration r ON r.regtype_id=rt.id WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL GROUP BY day ORDER BY day',
	'sessnoroom': "SELECT title AS \"Title\", trackname AS \"Track\", starttime || ' - ' || endtime AS \"Timeslot\" FROM confreg_conferencesession s LEFT JOIN confreg_track t ON t.id=s.track_id WHERE s.conference_id=%(confid)s AND status=1 AND room_id IS NULL",
	'sessnotrack': "SELECT title AS \"Title\", roomname AS \"Room\", starttime || ' - ' || endtime AS \"Timeslot\" FROM confreg_conferencesession s LEFT JOIN confreg_room r ON r.id=s.room_id WHERE s.conference_id=%(confid)s AND status=1 AND track_id IS NULL",
}
