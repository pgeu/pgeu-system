import os
import sys

import Image
import reportlab.lib.utils
reportlab.lib.utils.Image = Image

from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont

import qrencode

import badgetypes
from jinjabadge import render_jinja_badges

class BaseBadge(Flowable):
	def __init__(self, badgetype, reg):
		self.badgetype = badgetype
		self.reg = reg
		(self.width, self.height) = badgetype.getsize()

		self.resdir = '%s/res' % os.path.dirname(os.path.realpath(__file__))
		self.pglogo_white_name = '%s/pglogo_white.png' % self.resdir


	def wrap(self, *args):
		return (self.width, self.height)

	def draw(self):
		self.badgetype.draw(self)

	def setFill(self, r, g, b):
		self.canv.setFillColorRGB(float(r)/255, float(g)/255, float(b)/255)

	def setFillTuple(self, tup):
		self.setFill(tup[0], tup[1], tup[2])

	def ycoord(self, ymm, heightmm):
		return self.height - ymm * mm - heightmm*mm

	def drawDynamicParagraph(self, txt, x, y, width, height, color, bold=False, maxsize=None, alignment=TA_LEFT, verticalcenter=False):
		if not txt:
			return

		# Try to figure out the proper size
		if bold:
			fontname = 'DejaVu Serif Bold'
		else:
			fontname = 'DejaVu Serif'
		lines = txt.splitlines()
		# Max height is total height divided by lines divided by 1.2 since
		# we multiply the leading value with 1.2 later
		maxfont_height = int((height / len(lines)) / 1.2)
		if maxsize:
			maxfontsize = min(maxsize, maxfont_height)
		else:
			maxfontsize = maxfont_height
		for fontsize in range(4, maxfontsize):
			maxwidth = max([self.canv.stringWidth(l, fontname, fontsize) for l in lines])
			if maxwidth > width:
				fontsize -= 1
				break

		if verticalcenter:
			yoffset = (height - (len(lines) * fontsize)) / 2
		else:
			yoffset = 0

		txt = txt.replace("\n", "<br/>")
		style = ParagraphStyle('tempstyle')
		style.fontName = fontname
		style.textColor = color
		style.fontSize = fontsize
		style.leading = fontsize * 1.2
		style.alignment = alignment
		p = Paragraph(txt, style)
		(actualwidth, actualheight) = p.wrap(width, height)
		p.drawOn(self.canv, x, y+height-actualheight-yoffset)

	def drawQR(self, x, y):
		qrstring= "BEGIN:VCARD;VERSION:3.0;N:%s;%s\nFN:%s %s\nORG:%s\nEMAIL;TYPE=INTERNET,WORK:%s\nEND:VCARD" % (
			self.reg.lastname, self.reg.firstname,
			self.reg.firstname, self.reg.lastname,
			self.reg.company,
			self.reg.email, # XXX: filter?
			)
		(ver, size, qrimage) = qrencode.encode(qrstring, version=6)
		if size > 41:
			# Resize the image down to the same size to fit. That means
			# a QR code with really lots of info in it can become a little
			# bit blurry but that's needed to store all the info.
			size = 41

		# Resize the image to 4x the size, so the PDF looks better
		qrimage = qrimage.resize((size*4, size*4))

		self.canv.drawImage(ImageReader(qrimage),
							x, self.ycoord(y/mm, size*2/mm),
							size*2, size*2)



class BadgeBuilder(object):
	def __init__(self, conference, registrations):
		self.conference = conference
		self.registrations = registrations

		if not self.conference.jinjadir:
			raise Exception("No jinja template directory defined")

		# Register truetype fonts that we're going to end up embedding
		registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
		registerFont(TTFont('DejaVu Serif Bold', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif-Bold.ttf"))


	# Render of a specific type
	def render(self, output):
		if self.conference.jinjadir:
			return render_jinja_badges(self.conference, self.registrations, output)

		story = []
		for reg in self.registrations:
			story.append(BaseBadge(self.badgetype, reg))

		doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=10*mm, topMargin=5*mm, rightMargin=10*mm, bottomMargin=5*mm)
		doc.build(story)

