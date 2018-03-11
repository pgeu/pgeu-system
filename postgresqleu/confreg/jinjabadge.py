#!/usr/bin/env python

import json
import os.path
import argparse
import sys
import re
import operator

from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle

import jinja2
import jinja2.sandbox

alignments = {
	'left': TA_LEFT,
	'center': TA_CENTER,
	'right': TA_RIGHT,
}

def get_color(col):
	if isinstance(col, unicode) or isinstance(col, str):
		return colors.getAllNamedColors().get(col)
	elif isinstance(col, list):
		return colors.Color(*map(lambda x: x/255.0, col))
	else:
		raise Exception("Unknown color defintion type")

def getmm(struct, key):
	return struct[key] * mm

class JinjaBadge(Flowable):
	def __init__(self, js, imgpath):
		self.js = js
		self.imgpath = imgpath
		self.width = getmm(js, 'width')
		self.height = getmm(js, 'height')

	def draw(self):
		if self.js.get('border', False):
			self.canv.rect(0,0,self.width,self.height)

		for e in self.js['elements']:
			if e == {}:
				continue
			f = getattr(self, 'draw_' + e['type'], None)
			if callable(f):
				f(e)
			else:
				raise Exception("Unknown type %s" % e['type'])

	def calc_y(self, o):
		return self.height - getmm(o, 'y') - getmm(o, 'height')

	def draw_box(self, o):
		if o.has_key('fill'):
			self.canv.setFillColor(get_color(o['fill']))
			fill = 1
		else:
			fill = 0
		self.canv.rect(getmm(o, 'x'),
							self.calc_y(o),
							getmm(o, 'width'),
							getmm(o, 'height'),
							stroke=o['stroke'] and 1 or 0,
							fill=fill)

	def draw_line(self, o):
		self.canv.line(getmm(o, 'x'),
					   self.calc_y(o),
					   getmm(o, 'x') + getmm(o, 'width'),
					   self.calc_y(o) + getmm(o, 'height'))

	def resolve_image_path(self, src):
		p = os.path.normpath(os.path.join(self.imgpath, src))
		if not p.startswith(self.imgpath):
			raise Exception("Path escaping detected")
		# Else check if the file is there
		if os.path.isfile(p):
			return p

		raise Exception("File not found: %s" % src)

	def draw_image(self, o):
		p = self.resolve_image_path(o['src'])
		self.canv.drawImage(p,
								 getmm(o, 'x'),
								 self.calc_y(o),
								 getmm(o, 'width'),
								 getmm(o, 'height'),
								 o.get('mask', 'auto'),
								 preserveAspectRatio=o.get('preserveAspect', False),
								 )

	def draw_paragraph(self, o):
		# Attempt to draw a paragraph that can dynamically change the font size
		# as necessary.
		fontname = 'DejaVu Serif{0}'.format(o.get('bold', False) and ' Bold' or '')
		lines = o['text'].splitlines()

		if len(lines) == 0:
			# Don't try to draw empty lines
			return

		# Max height is total height divided by lines divided by 1.2 since
		# we multiply the leading value with 1.2 later
		maxsize = o.get('maxsize', None)
		maxfont_height = int((getmm(o, 'height') / len(lines)) / 1.2)
		if maxsize:
			maxfontsize = min(maxsize, maxfont_height)
		else:
			maxfontsize = maxfont_height
		for fontsize in range(4, maxfontsize):
			maxwidth = max([self.canv.stringWidth(l, fontname, fontsize) for l in lines])
			if maxwidth > getmm(o, 'width'):
				fontsize -= 1
				break

		if o.get('verticalcenter', False):
			yoffset = (getmm(o, 'height') - (len(lines) * fontsize)) / 2
		else:
			yoffset = 0

		txt = o['text'].replace("\n", "<br/>")
		style = ParagraphStyle('tempstyle')
		style.fontName = fontname
		style.textColor = get_color(o.get('color', 'black'))
		style.fontSize = fontsize
		style.leading = fontsize * 1.2
		style.alignment = alignments[o.get('align', 'left')]
		p = Paragraph(txt, style)
		(actualwidth, actualheight) = p.wrap(getmm(o, 'width'), getmm(o, 'height'))
		p.drawOn(self.canv, getmm(o, 'x'), self.calc_y(o)+getmm(o, 'height')-actualheight-yoffset)


def escapejson_filter(v):
	# Dumping a string/unicode to json will add double quotes at beginning and end. Strip
	# those, but only one if there is more than one.
	return re.sub(r'^"|"$', '', json.dumps(v))

def test_inlist(v,l):
	return v in l

class JinjaRenderer(object):
	def __init__(self, rootdir, debug=False, border=False, pagebreaks=False):
		self.templatedir = os.path.join(rootdir, 'templates')
		self.debug = debug
		self.border = border
		self.pagebreaks = pagebreaks

		registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
		registerFont(TTFont('DejaVu Serif Bold', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif-Bold.ttf"))

		if not os.path.exists(os.path.join(self.templatedir, 'badge.json')):
			raise Exception("badge.json not found for conference")

		with open(os.path.join(self.templatedir, 'badge.json')) as f:
			env = jinja2.sandbox.SandboxedEnvironment()
			env.filters.update({
				'escapejson': escapejson_filter,
				'yesno': lambda b,v: v.split(',')[not b],
			})
			env.tests.update({
				'inlist': test_inlist,
				'equalto': operator.eq,
			})
			self.template = env.from_string(f.read())

		self.context = self._load_context(os.path.join(self.templatedir, 'context.json'))
		self.context.update(self._load_context(os.path.join(self.templatedir, 'context.override.json')))

		self.staticdir = os.path.join(rootdir, 'static')
		if not os.path.isdir(self.staticdir):
			if debug:
				print "Static directory {0} does not exist, ignoring.".format(self.staticdir)
			self.staticdir = None

		self.story = []

	def _load_context(self, jsonfile):
		if os.path.isfile(jsonfile):
			with open(jsonfile) as f:
				return json.load(f)
		else:
			return {}

	def add_badge(self, reg):
		ctx = {
			'reg': reg,
		}
		ctx.update(self.context)
		s = self.template.render(**ctx)
		try:
			js = json.loads(s)
		except ValueError, e:
			if self.debug:
				print "JSON parse failed. Template output:"
				print s
				print "------------------------"
				print "JSON parse failed: %s" % e
				print "see template output above."
				sys.exit(1)
			else:
				raise Exception("JSON parse failed.")

		if not 'border' in js:
			js['border'] = self.border
		self.story.append(JinjaBadge(js, self.staticdir))

		if not 'forcebreaks' in js:
			js['forcebreaks'] = self.pagebreaks
		if js.get('forcebreaks', False):
			self.story.append(PageBreak())

	def render(self, output):
		doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=10*mm, topMargin=5*mm, rightMargin=10*mm, bottomMargin=5*mm)
		doc.build(self.story)


# Render badges from within the website scope, meaning we have access to the
# django objects here.
def render_jinja_badges(conference, registrations, output, border, pagebreaks):
	renderer = JinjaRenderer(conference.jinjadir, border=border, pagebreaks=pagebreaks)

	for reg in registrations:
		renderer.add_badge(reg.safe_export())

	renderer.render(output)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Render jinja based badges')
	parser.add_argument('repopath', type=str, help='Template repository directory')
	parser.add_argument('attendeelist', type=str, help='JSON file with attendee list')
	parser.add_argument('outputfile', type=str, help='Name of output PDF file')
	parser.add_argument('--borders', action='store_true', help='Enable borders on written file')
	parser.add_argument('--pagebreaks', action='store_true', help='Enable pagebreaks on written file')

	args = parser.parse_args()

	renderer = JinjaRenderer(args.repopath, debug=True, border=args.borders, pagebreaks=args.pagebreaks)

	with open(args.attendeelist) as f:
		a = json.load(f)

	for reg in a:
		renderer.add_badge(reg)

	with open(args.outputfile, 'wb') as output:
		renderer.render(output)
