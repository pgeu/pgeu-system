#!/usr/bin/env python
# -*- coding: utf-8 -*-

from decimal import Decimal

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.platypus.tables import Table, TableStyle
from reportlab.platypus.flowables import Image
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
import qrencode
import cStringIO as StringIO

class PDFBase(object):
    def __init__(self, recipient, invoicenum, imagedir, currency):
        self.pdfdata = StringIO.StringIO()
        self.canvas = Canvas(self.pdfdata)

        self.recipient = recipient
        self.invoicenum = invoicenum
        self.imagedir = imagedir or '.'
        self.currency = currency or '€'

        self.preview = False

        self.canvas.setTitle("PostgreSQL Europe Invoice #%s" % self.invoicenum)
        self.canvas.setSubject("PostgreSQL Europe Invoice #%s" % self.invoicenum)
        self.canvas.setAuthor("PostgreSQL Europe")
        self.canvas._doc.info.producer = "PostgreSQL Europe Invoicing System"

        registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
        registerFont(TTFont('DejaVu Serif Italic', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif-Italic.ttf"))
        registerFont(TTFont('DejaVu Serif Bold', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif-Bold.ttf"))

    def trimstring(self, s, maxlen, fontname, fontsize):
        while len(s) > 5:
            if self.canvas.stringWidth(s, fontname, fontsize) <= maxlen:
                return s
            s = s[:len(s)-2]
        return s

    def textlines(self, t, lines):
        for l in lines.splitlines():
            t.textLine(l)

    def _draw_multiline_aligned(self, txt, left, top, width, height):
        t = txt.replace("\n", "<br/>")
        style = ParagraphStyle('temp')
        style.fontName = 'DejaVu Serif'
        style.fontSize = 9
        style.leading = 9 * 1.2
        p = Paragraph(t, style)
        (actualwidth, actualheight) = p.wrap(width, height)
        p.drawOn(self.canvas, left, top-actualheight)

    def _pageheader(self):
        if self.preview:
            t = self.canvas.beginText()
            t.setTextOrigin(6*cm, 4*cm)
            t.setFont("DejaVu Serif Italic", 70)
            t.setFillColorRGB(0.9, 0.9, 0.9)
            t.textLine("PREVIEW PREVIEW")
            self.canvas.rotate(45)
            self.canvas.drawText(t)
            self.canvas.rotate(-45)

        im = Image("%s/PostgreSQL_logo.1color_blue.300x300.png" % self.imagedir, width=3*cm, height=3*cm)
        im.drawOn(self.canvas, 2*cm, 25*cm)
        t = self.canvas.beginText()
        t.setFillColor(colors.black)
        t.setFont("DejaVu Serif", 9)
        t.setTextOrigin(6*cm, 27.5*cm)
        self.textlines(t, """PostgreSQL Europe
Carpeaux Diem
13, rue du Square Carpeaux
75018 PARIS
France
SIREN 823839535
VAT# FR36823839535
""")
        self.canvas.drawText(t)

        self._draw_multiline_aligned("""Your contact: Guillaume Lelarge
Function: PostgreSQL Europe Treasurer
E-mail: treasurer@postgresql.eu""",
                                     2*cm, 23.5*cm, 9*cm, 4*cm)

        self._draw_multiline_aligned(u"To:\n%s" % self.recipient,
                                     11*cm, 23.5*cm, 9*cm, 4*cm)

        p = self.canvas.beginPath()
        p.moveTo(2*cm, 18.9*cm)
        p.lineTo(19*cm, 18.9*cm)
        self.canvas.drawPath(p)


class PDFInvoice(PDFBase):
    def __init__(self, title, recipient, invoicedate, duedate, invoicenum=None, imagedir=None, currency='€', preview=False, receipt=False, bankinfo=True, totalvat=0, reverse_vat=None, paymentlink=None, **kw):
        super(PDFInvoice, self).__init__(recipient, invoicenum, imagedir, currency)

        self.title = title
        self.invoicedate = invoicedate
        self.duedate = duedate
        self.preview = preview
        self.receipt = receipt
        self.bankinfo = bankinfo
        self.totalvat = totalvat
        self.reverse_vat = reverse_vat
        self.paymentlink = paymentlink
        self.rows = []

        if self.receipt:
            # Never include bank info on receipts
            self.bankinfo = False


    def addrow(self, title, cost, count, vatrate):
        self.rows.append((title, cost, count, vatrate, vatrate and vatrate.vatpercent or 0))


    ROWS_PER_PAGE = 14
    def save(self):
        # We can fit ROWS_PER_PAGE rows on one page. We might want to do something
        # cute to avoid a single row on it's own page in the future, but
        # for now, just split it evenly.
        for pagenum in range(0, (len(self.rows)-1)/self.ROWS_PER_PAGE+1):
            self._pageheader()
            islastpage = (pagenum == (len(self.rows)-1)/self.ROWS_PER_PAGE)

            if len(self.rows) > self.ROWS_PER_PAGE:
                suffix = " (page %s/%s)" % (pagenum+1, len(self.rows)/self.ROWS_PER_PAGE+1)
            else:
                suffix = ''

            self.canvas.setFont('DejaVu Serif Bold', 12)
            # Center between 2 and 19 is 10.5
            self.canvas.drawCentredString(10.5*cm, 19*cm, self.title)
            self.canvas.setFont('DejaVu Serif', 9)

            if self.invoicenum:
                if self.receipt:
                    self.canvas.drawCentredString(10.5*cm, 18.5*cm, "Receipt for invoice number %s%s" % (self.invoicenum, suffix))
                else:
                    self.canvas.drawCentredString(10.5*cm, 18.5*cm, "Invoice number %s - %s%s" % (self.invoicenum, self.invoicedate.strftime("%B %d, %Y"), suffix))
                self.canvas.setFont('DejaVu Serif Bold', 10)
                if self.receipt:
                    self.canvas.drawCentredString(17*cm, 28*cm, "Receipt #%s" % self.invoicenum)
                else:
                    self.canvas.drawCentredString(17*cm, 28*cm, "Invoice #%s" % self.invoicenum)
            else:
                self.canvas.drawCentredString(10.5*cm, 18.5*cm, "Receipt - %s%s" % (self.invoicedate.strftime("%B %d, %Y"), suffix))

            if pagenum == 0:
                firstcol = "Item"
            else:
                firstcol = "Item - continued from page %s" % pagenum
            tbldata = [[firstcol, "Quantity", "Ex VAT", "VAT", "Incl VAT"]]
            tblcols = len(tbldata[0])

            tbldata.extend([(self.trimstring(title, 9.5*cm, "DejaVu Serif", 8),
                             count,
                             "%.2f %s" % (cost, self.currency),
                             vatrate and vatrate.shortstr or "No VAT",
                             "%.2f %s" % ((cost * count) * (1+(vatpercent/Decimal(100))), self.currency))
                            for title, cost, count, vatrate, vatpercent in self.rows[pagenum*self.ROWS_PER_PAGE:(pagenum+1)*self.ROWS_PER_PAGE]])
            style = [
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 0), (tblcols-1, 0), colors.lightgrey),
                ('ALIGN', (1, 0), (tblcols-1, -1), 'RIGHT'),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),
                ('OUTLINE', (0, 0), (-1, -1), 1, colors.black),
            ]
            if islastpage:
                totalexcl = sum([cost*count for title, cost, count, vatrate, vatpercent in self.rows])
                totalvat = sum([(cost*count*(vatpercent/Decimal(100))).quantize(Decimal('0.01')) for title, cost, count, vatrate, vatpercent in self.rows])
                totalincl = sum([(cost*count*(1+vatpercent/Decimal(100))).quantize(Decimal('0.01')) for title, cost, count, vatrate, vatpercent in self.rows])
                if self.totalvat > 0 and totalvat != self.totalvat:
                    raise Exception("Specified total VAT {0} does not match calculated VAT {1}".format(self.totalvat, totalvat))

                if self.reverse_vat:
                    if totalvat != 0:
                        raise Exception("Can't use reverse VAT and specified VAT at the same time!")
                    vathdr = 'Total VAT *'
                    vatstr = "0 %s *" % (self.currency)
                else:
                    vathdr = 'Total VAT'
                    vatstr = '%.2f %s' % (totalvat, self.currency)

                tbldata.extend([
                    ('Total excl VAT', '', '', '', '%.2f %s' % (totalexcl, self.currency)),
                    (vathdr, '', '', '', vatstr),
                    ('Total incl VAT', '', '', '', '%.2f %s' % (totalincl, self.currency)),
                ])
                style.extend([
                    ('SPAN', (0, -3), (3, -3)),
                    ('SPAN', (0, -2), (3, -2)),
                    ('SPAN', (0, -1), (3, -1)),
                    ('ALIGN', (0, -3), (0, -1), 'RIGHT'),
                    ('LINEABOVE', (-4, -3), (-1, -3), 2, colors.black),
                ])
            else:
                tbldata.append(['          Continued on page %s' % (pagenum + 2), '', '', ''])
                style.append(('ALIGN', (0, -1), (-1, -1), 'CENTER'))
                style.append(('FONT', (0, -1), (-1, -1), 'DejaVu Serif Italic'))

            t = Table(tbldata, [9.5*cm, 1.5*cm, 2.5*cm, 2*cm, 2.5*cm])
            t.setStyle(TableStyle(style))
            w, h = t.wrapOn(self.canvas, 10*cm, 10*cm)
            t.drawOn(self.canvas, 2*cm, 18*cm-h)

            if self.receipt:
                self.canvas.drawCentredString(10.5*cm, 17.3*cm-h, "This invoice was paid %s" % self.duedate.strftime("%B %d, %Y"))
            else:
                self.canvas.drawCentredString(10.5*cm, 17.3*cm-h, "This invoice is due: %s" % self.duedate.strftime("%B %d, %Y"))


            if islastpage:
                if not self.receipt:
                    t = self.canvas.beginText()
                    t.setTextOrigin(2*cm, 1.5*cm)
                    t.setFont("DejaVu Serif", 6)
                    self.textlines(t, """Penalty for late payment: Three times the French Legal Interest Rate on the due amount.
Compensation due for any recovery costs incurred: €40
Discount for prepayment: None.
""")
                    self.canvas.drawText(t)

                if self.bankinfo:
                    t = self.canvas.beginText()
                    t.setTextOrigin(13*cm, 3*cm)
                    t.setFont("DejaVu Serif Bold", 9)
                    t.textLine("Bank references")

                    t.setFont("DejaVu Serif", 7)
                    self.textlines(t, """CCM PARIS 1-2 LOUVRE MONTORGUEIL
28 RUE ETIENNE MARCEL
75002 PARIS
FRANCE
IBAN: FR76 1027 8060 3100 0205 2290 114
BIC: CMCIFR2A
""")

                    self.canvas.drawText(t)

                if self.paymentlink:
                    style = ParagraphStyle('temp')
                    style.fontName = 'DejaVu Serif'
                    style.fontSize = 5
                    p = Paragraph('Payment details and instructions:<br/><nobr><a href="{0}">{0}</a></nobr>'.format(self.paymentlink), style)
                    p.wrapOn(self.canvas, 12*cm, 2*cm)
                    p.drawOn(self.canvas, 2*cm, 3.5*cm)

                    (ver, size, qrimage) = qrencode.encode(self.paymentlink)
                    qrimage = qrimage.resize((size*4, size*4))
                    self.canvas.drawImage(ImageReader(qrimage),
                                          2*cm, 1.8*cm,
                                          1.5*cm, 1.5*cm)

                if self.reverse_vat:
                    t = self.canvas.beginText()
                    t.setTextOrigin(2*cm, 4.8*cm)
                    t.setFont("DejaVu Serif", 6)
                    self.textlines(t, "* Services subject to the reverse charge - VAT to be accounted for by the recipient as per Article 196 of Council Directive 2006/112/EC")
                    self.canvas.drawText(t)

            # Finish this page off, and optionally loop to another one
            self.canvas.showPage()

        # Last page is finished, flush the PDF output
        self.canvas.save()

        return self.pdfdata



class PDFRefund(PDFBase):
    def __init__(self, recipient, invoicedate, refunddate, invoicenum, invoiceamount, invoicevat, refundamount, refundvat, imagedir, currency, paymentmethod):
        self.recipient = recipient
        self.invoicedate = invoicedate
        self.refunddate = refunddate
        self.invoiceamount = invoiceamount
        self.invoicevat = invoicevat
        self.refundamount = refundamount
        self.refundvat = refundvat
        self.paymentmethod = paymentmethod

        super(PDFRefund, self).__init__(recipient, invoicenum, imagedir, currency)

    def save(self):
        self._pageheader()

        self.canvas.drawCentredString(10.5*cm, 19*cm, "REFUND NOTE FOR INVOICE NUMBER {0}".format(self.invoicenum))

        tblpaid = [
            ["Amount paid"],
            ["Item", "Amount"],
            ["Amount", "{0:.2f} {1}".format(self.invoiceamount, self.currency)],
        ]
        tblrefunded = [
            ["Amount refunded"],
            ["Item", "Amount"],
            ["Amount", "{0:.2f} {1}".format(self.refundamount, self.currency)],
        ]
        if self.invoicevat:
            tblpaid.extend([
                ["VAT", "{0:.2f} {1}".format(self.invoicevat, self.currency)],
                ["", "{0:.2f} {1}".format(self.invoiceamount + self.invoicevat, self.currency)],
            ])
            tblrefunded.extend([
                ["VAT", "{0:.2f} {1}".format(self.refundvat, self.currency)],
                ["", "{0:.2f} {1}".format(self.refundamount + self.refundvat, self.currency)],
            ])

        style = [
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('LINEBELOW', (0, 1), (-1, 1), 1, colors.black),
            ('OUTLINE', (0, 0), (-1, -1), 1, colors.black),
        ]
        if self.invoicevat:
            style.append(
                ('LINEABOVE', (-1, -1), (-1, -1), 2, colors.black),
            )

        t = Table(tblpaid, [10.5*cm, 2.5*cm, 1.5*cm, 2.5*cm])
        t.setStyle(TableStyle(style))
        w, h = t.wrapOn(self.canvas, 10*cm, 10*cm)
        t.drawOn(self.canvas, (self.canvas._pagesize[0]-w)/2, 18*cm-h)

        t = Table(tblrefunded, [10.5*cm, 2.5*cm, 1.5*cm, 2.5*cm])
        t.setStyle(TableStyle(style))
        w, h = t.wrapOn(self.canvas, 10*cm, 10*cm)
        t.drawOn(self.canvas, (self.canvas._pagesize[0]-w)/2, 18*cm-h*2-1*cm)

        self.canvas.drawCentredString(10.5*cm, 17.3*cm-h*2 - 2*cm, "This refund was issued {0}".format(self.refunddate.strftime("%B %d, %Y")))

        if self.paymentmethod:
            self.canvas.drawCentredString(10.5*cm, 17.3*cm-h*2-3*cm, "Refunded to the original form of payment: {0}.".format(self.paymentmethod))

        self.canvas.showPage()
        self.canvas.save()

        return self.pdfdata
