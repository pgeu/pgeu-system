#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus.tables import Table, TableStyle
from reportlab.platypus.flowables import Image
import cStringIO as StringIO

class PDFInvoice(object):
	def __init__(self, recipient, invoicedate, duedate, invoicenum=None, imagedir=None, currency='€'):
		self.pdfdata = StringIO.StringIO()
		self.canvas = Canvas(self.pdfdata)
		self.recipient = recipient
		self.invoicenum = invoicenum
		self.invoicedate = invoicedate
		self.duedate = duedate
		self.imagedir = imagedir or '.'
		self.currency = currency or '€'
		self.rows = []

		self.canvas.setTitle("PostgreSQL Europe Invoice #%s" % self.invoicenum)
		self.canvas.setSubject("PostgreSQL Europe Invoice #%s" % self.invoicenum)
		self.canvas.setAuthor("PostgreSQL Europe")
		self.canvas._doc.info.producer = "PostgreSQL Europe Invoicing System"

	def addrow(self, title, cost, count=1):
		self.rows.append((title, cost, count,))


	def trimstring(self, s, maxlen, fontname, fontsize):
		while len(s) > 5:
			if self.canvas.stringWidth(s, fontname, fontsize) <= maxlen:
				return s
			s = s[:len(s)-2]

	def save(self):
		im = Image("%s/PostgreSQL_logo.1color_blue.300x300.png" % self.imagedir, width=3*cm, height=3*cm)
		im.drawOn(self.canvas, 2*cm, 25*cm)
		t = self.canvas.beginText()
		t.setTextOrigin(6*cm, 27.5*cm)
		t.textLines("""PostgreSQL Europe
Carpeaux Diem
13, rue du Square Carpeaux
75018 PARIS
France
""")
		self.canvas.drawText(t)

		t = self.canvas.beginText()
		t.setTextOrigin(2*cm, 23*cm)
		t.setFont("Times-Roman", 10)
		t.textLine("")
		t.textLines("""
Your contact: Jean-Paul Argudo
Function: PostgreSQL Europe Treasurer
E-mail: treasurer@postgresql.eu
""")
		self.canvas.drawText(t)

		t = self.canvas.beginText()
		t.setTextOrigin(11*cm, 23*cm)
		t.setFont("Times-Italic", 11)
		t.textLine("To:")
		t.setFont("Times-Roman", 11)
		t.textLines(self.recipient)
		self.canvas.drawText(t)

		# Center between 2 and 19 is 10.5
		if self.invoicenum:
			self.canvas.drawCentredString(10.5*cm,19*cm, "INVOICE NUMBER %s - %s" % (self.invoicenum, self.invoicedate.strftime("%B %d, %Y")))
			#2010-41 - October, 25th 2010")
		else:
			self.canvas.drawCentredString(10.5*cm,19*cm, "RECEIPT - %s" % self.invoicedate.strftime("%B %d, %Y"))

		p = self.canvas.beginPath()
		p.moveTo(2*cm, 18.9*cm)
		p.lineTo(19*cm, 18.9*cm)
		self.canvas.drawPath(p)

		tbldata = [["Item", "Price", "Count", "Amount"], ]
		tbldata.extend([(self.trimstring(title, 10.5*cm, "Times-Roman", 10),
						 "%.2f %s" % (cost, self.currency),
						 count,
						 "%.2f %s" % ((cost * count), self.currency))
						for title,cost, count in self.rows])
		tbldata.append(['','','Total',"%.2f %s" % (sum([cost*count for title,cost,count in self.rows]),self.currency)])

		t = Table(tbldata, [10.5*cm, 2.5*cm, 1.5*cm, 2.5*cm])
		t.setStyle(TableStyle([
					('BACKGROUND',(0,0),(3,0),colors.lightgrey),
					('ALIGN',(1,0),(3,-1),'RIGHT'),
					('LINEBELOW',(0,0),(-1,0), 2, colors.black),
					('OUTLINE', (0,0), (-1, -1), 1, colors.black),
					('LINEABOVE', (-2,-1), (-1, -1), 2, colors.black),
				   ]))
		w,h = t.wrapOn(self.canvas,10*cm,10*cm)
		t.drawOn(self.canvas, 2*cm, 18*cm-h)

		self.canvas.drawCentredString(10.5*cm,17.3*cm-h, "This invoice is due: %s" % self.duedate.strftime("%B %d, %Y"))


		t = self.canvas.beginText()
		t.setTextOrigin(2*cm, 5*cm)
		t.setFont("Times-Italic", 10)
		t.textLine("PostgreSQL Europe is a French non-profit under the French 1901 Law.")
		t.textLine("")

		t.setFont("Times-Bold", 10)
		t.textLine("Bank references / Références bancaires / Bankverbindungen / Referencias bancarias")

		t.setFont("Times-Roman", 8)
		t.textLines("""BNP PARISBAS - MONTROUGE REPUBLIQUE
110, Avenue de la République
92120 MONTROUGE
FRANCE
IBAN: FR76 3000 4001 6200 0100 7536 333
BIC: BNPAFRPPBBT
""")
		self.canvas.drawText(t)


		self.canvas.showPage()
		self.canvas.save()

		return self.pdfdata
