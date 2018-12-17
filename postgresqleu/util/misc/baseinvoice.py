#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from decimal import Decimal

from reportlab.pdfgen.canvas import Canvas
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

from django.conf import settings

from postgresqleu.util.reporttools import cm


class PDFBase(object):
    logo = None
    headertext = None
    sendertext = settings.ORG_NAME

    def __init__(self, recipient):
        self.pdfdata = StringIO.StringIO()
        self.canvas = Canvas(self.pdfdata)

        self.recipient = recipient

        self.preview = False

        self.canvas.setTitle(self.title)
        self.canvas.setSubject(self.title)
        self.canvas.setAuthor(settings.ORG_NAME)
        self.canvas._doc.info.producer = "{0} Invoicing System".format(settings.ORG_NAME)

        registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
        registerFont(TTFont('DejaVu Serif Italic', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif-Italic.ttf"))
        registerFont(TTFont('DejaVu Serif Bold', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif-Bold.ttf"))

    def trimstring(self, s, maxlen, fontname, fontsize):
        while len(s) > 5:
            if self.canvas.stringWidth(s, fontname, fontsize) <= maxlen:
                return s
            s = s[:len(s) - 2]
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
        p.drawOn(self.canvas, left, top - actualheight)

    def draw_header(self):
        if self.preview:
            t = self.canvas.beginText()
            t.setTextOrigin(cm(6), cm(4))
            t.setFont("DejaVu Serif Italic", 70)
            t.setFillColorRGB(0.9, 0.9, 0.9)
            t.textLine("PREVIEW PREVIEW")
            self.canvas.rotate(45)
            self.canvas.drawText(t)
            self.canvas.rotate(-45)

        if self.logo:
            im = Image(self.logo, width=cm(3), height=cm(3))
            im.drawOn(self.canvas, cm(2), cm(25))

        if self.headertext:
            t = self.canvas.beginText()
            t.setFillColor(colors.black)
            t.setFont("DejaVu Serif", 9)
            t.setTextOrigin(cm(6), cm(27.5))
            self.textlines(t, self.headertext)
            self.canvas.drawText(t)

        if self.sendertext:
            self._draw_multiline_aligned(self.sendertext,
                                         cm(2), cm(23.5), cm(9), cm(4))

        self._draw_multiline_aligned(u"To:\n%s" % self.recipient,
                                     cm(11), cm(23.5), cm(9), cm(4))

        p = self.canvas.beginPath()
        p.moveTo(cm(2), cm(18.9))
        p.lineTo(cm(19), cm(18.9))
        self.canvas.drawPath(p)


class BaseInvoice(PDFBase):
    bankinfotext = None
    paymentterms = None
    ROWS_PER_PAGE = 14

    def __init__(self, title, recipient, invoicedate, duedate, invoicenum, preview=False, receipt=False, bankinfo=True, totalvat=0, reverse_vat=None, paymentlink=None, **kw):
        self.title = title
        self.invoicedate = invoicedate
        self.duedate = duedate
        self.invoicenum = invoicenum
        self.preview = preview
        self.receipt = receipt
        self.bankinfo = bankinfo
        self.totalvat = totalvat
        self.reverse_vat = reverse_vat
        self.paymentlink = paymentlink

        super(BaseInvoice, self).__init__(recipient)

        self.rows = []

        if self.receipt:
            # Never include bank info on receipts
            self.bankinfo = False

    def addrow(self, title, cost, count, vatrate):
        self.rows.append((title, cost, count, vatrate, vatrate and vatrate.vatpercent or 0))

    def save(self):
        # We can fit ROWS_PER_PAGE rows on one page. We might want to do something
        # cute to avoid a single row on it's own page in the future, but
        # for now, just split it evenly.
        for pagenum in range(0, (len(self.rows) - 1) / self.ROWS_PER_PAGE + 1):
            self.draw_header()
            islastpage = (pagenum == (len(self.rows) - 1) / self.ROWS_PER_PAGE)

            if len(self.rows) > self.ROWS_PER_PAGE:
                suffix = " (page %s/%s)" % (pagenum + 1, len(self.rows) / self.ROWS_PER_PAGE + 1)
            else:
                suffix = ''

            self.canvas.setFont('DejaVu Serif Bold', 12)
            # Center between 2 and 19 is 10.5
            self.canvas.drawCentredString(cm(10.5), cm(19), self.title)
            self.canvas.setFont('DejaVu Serif', 9)

            if self.invoicenum:
                if self.receipt:
                    self.canvas.drawCentredString(cm(10.5), cm(18.5), "Receipt for invoice number %s%s" % (self.invoicenum, suffix))
                else:
                    self.canvas.drawCentredString(cm(10.5), cm(18.5), "Invoice number %s - %s%s" % (self.invoicenum, self.invoicedate.strftime("%B %d, %Y"), suffix))
                self.canvas.setFont('DejaVu Serif Bold', 10)
                if self.receipt:
                    self.canvas.drawCentredString(cm(17), cm(28), "Receipt #%s" % self.invoicenum)
                else:
                    self.canvas.drawCentredString(cm(17), cm(28), "Invoice #%s" % self.invoicenum)
            else:
                self.canvas.drawCentredString(cm(10.5), cm(18.5), "Receipt - %s%s" % (self.invoicedate.strftime("%B %d, %Y"), suffix))

            if pagenum == 0:
                firstcol = "Item"
            else:
                firstcol = "Item - continued from page %s" % pagenum

            if settings.EU_VAT:
                tbldata = [[firstcol, "Quantity", "Ex VAT", "VAT", "Incl VAT"]]
            else:
                tbldata = [[firstcol, "Quantity", "Price", "Total"]]
            tblcols = len(tbldata[0])

            if settings.EU_VAT:
                tbldata.extend([(self.trimstring(title, cm(9.5), "DejaVu Serif", 8),
                                 count,
                                 "%.2f %s" % (cost, settings.CURRENCY_SYMBOL),
                                 vatrate and vatrate.shortstr or "No VAT",
                                 "%.2f %s" % ((cost * count) * (1 + (vatpercent / Decimal(100))), settings.CURRENCY_SYMBOL))
                                for title, cost, count, vatrate, vatpercent in self.rows[pagenum * self.ROWS_PER_PAGE:(pagenum + 1) * self.ROWS_PER_PAGE]])
            else:
                tbldata.extend([(self.trimstring(title, cm(9.5), "DejaVu Serif", 8),
                                 count,
                                 "%.2f %s" % (cost, settings.CURRENCY_SYMBOL),
                                 "%.2f %s" % ((cost * count), settings.CURRENCY_SYMBOL))
                                for title, cost, count, vatrate, vatpercent in self.rows[pagenum * self.ROWS_PER_PAGE:(pagenum + 1) * self.ROWS_PER_PAGE]])

            style = [
                # Set global font size
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                # Right-align all columnsexcept the first one (item name)
                ('ALIGN', (1, 0), (tblcols - 1, -1), 'RIGHT'),
                # Draw header line background in light gray and line under it
                ('BACKGROUND', (0, 0), (tblcols - 1, 0), colors.lightgrey),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),
                # Draw an outline around the whole table
                ('OUTLINE', (0, 0), (-1, -1), 1, colors.black),
            ]

            if islastpage:
                totalexcl = sum([cost * count for title, cost, count, vatrate, vatpercent in self.rows])

                if settings.EU_VAT:
                    # When EU vat enabled, calculate total fields both with and without VAT,
                    # and special-case the reverse-VAT situation.
                    totalvat = sum([(cost * count * (vatpercent / Decimal(100))).quantize(Decimal('0.01')) for title, cost, count, vatrate, vatpercent in self.rows])
                    totalincl = sum([(cost * count * (1 + vatpercent / Decimal(100))).quantize(Decimal('0.01')) for title, cost, count, vatrate, vatpercent in self.rows])

                    if self.totalvat > 0 and totalvat != self.totalvat:
                        raise Exception("Specified total VAT {0} does not match calculated VAT {1}".format(self.totalvat, totalvat))

                    if self.reverse_vat:
                        if totalvat != 0:
                            raise Exception("Can't use reverse VAT and specified VAT at the same time!")
                        vathdr = 'Total VAT *'
                        vatstr = "0 %s *" % (settings.CURRENCY_SYMBOL, )
                    else:
                        vathdr = 'Total VAT'
                        vatstr = '%.2f %s' % (totalvat, settings.CURRENCY_SYMBOL)

                    tbldata.extend([
                        ('Total excl VAT', '', '', '', '%.2f %s' % (totalexcl, settings.CURRENCY_SYMBOL)),
                        (vathdr, '', '', '', vatstr),
                        ('Total incl VAT', '', '', '', '%.2f %s' % (totalincl, settings.CURRENCY_SYMBOL)),
                    ])

                    style.extend([
                        # For the tree "total excl", "cat", "total incl" lines, span the
                        # cells together and alight right, and draw a line above them.
                        ('SPAN', (0, -3), (3, -3)),
                        ('SPAN', (0, -2), (3, -2)),
                        ('SPAN', (0, -1), (3, -1)),
                        ('ALIGN', (0, -3), (0, -1), 'RIGHT'),
                        ('LINEABOVE', (-4, -3), (-1, -3), 2, colors.black),
                    ])
                else:
                    # No EU vat, so just a simple total
                    tbldata.extend([
                        ('Total', '', '',
                         '%.2f %s' % (totalexcl, settings.CURRENCY_SYMBOL)),
                    ])

                    # Merge the cells of the total line together, right-align them, and
                    # draw a line above them.
                    style.extend([
                        ('SPAN', (0, -1), (2, -1)),
                        ('ALIGN', (0, -1), (0, -1), 'RIGHT'),
                        ('LINEABOVE', (-3, -1), (-1, -1), 2, colors.black),
                    ])

            else:
                tbldata.append(['          Continued on page %s' % (pagenum + 2), '', '', ''])
                style.append(('ALIGN', (0, -1), (-1, -1), 'CENTER'))
                style.append(('FONT', (0, -1), (-1, -1), 'DejaVu Serif Italic'))

            t = Table(tbldata, [cm(9.5), cm(1.5), cm(2.5), cm(2), cm(2.5)])
            t.setStyle(TableStyle(style))
            w, h = t.wrapOn(self.canvas, cm(10), cm(10))
            t.drawOn(self.canvas, cm(2), cm(18) - h)

            if self.receipt:
                self.canvas.drawCentredString(cm(10.5), cm(17.3) - h, "This invoice was paid %s" % self.duedate.strftime("%B %d, %Y"))
            else:
                self.canvas.drawCentredString(cm(10.5), cm(17.3) - h, "This invoice is due: %s" % self.duedate.strftime("%B %d, %Y"))

            if islastpage:
                self.draw_footer()

            # Finish this page off, and optionally loop to another one
            self.canvas.showPage()

        # Last page is finished, flush the PDF output
        self.canvas.save()

        return self.pdfdata

    def draw_footer(self):
        if not self.receipt and self.paymentterms:
            t = self.canvas.beginText()
            t.setTextOrigin(cm(2), cm(1.5))
            t.setFont("DejaVu Serif", 6)
            self.textlines(t, self.paymentterms)
            self.canvas.drawText(t)

        if self.bankinfo and self.bankinfotext:
            t = self.canvas.beginText()
            t.setTextOrigin(cm(13), cm(3))
            t.setFont("DejaVu Serif Bold", 9)
            t.textLine("Bank references")

            t.setFont("DejaVu Serif", 7)
            self.textlines(t, self.bankinfotext)
            self.canvas.drawText(t)

        if self.paymentlink:
            style = ParagraphStyle('temp')
            style.fontName = 'DejaVu Serif'
            style.fontSize = 5
            p = Paragraph('Payment details and instructions:<br/><nobr><a href="{0}">{0}</a></nobr>'.format(self.paymentlink), style)
            p.wrapOn(self.canvas, cm(12), cm(2))
            p.drawOn(self.canvas, cm(2), cm(3.5))

            (ver, size, qrimage) = qrencode.encode(self.paymentlink)
            qrimage = qrimage.resize((size * 4, size * 4))
            self.canvas.drawImage(ImageReader(qrimage),
                                  cm(2), cm(1.8),
                                  cm(1.5), cm(1.5))

            if self.reverse_vat:
                t = self.canvas.beginText()
                t.setTextOrigin(cm(2), cm(4.8))
                t.setFont("DejaVu Serif", 6)
                self.textlines(t, "* Services subject to the reverse charge - VAT to be accounted for by the recipient as per Article 196 of Council Directive 2006/112/EC")
                self.canvas.drawText(t)


class BaseRefund(PDFBase):
    def __init__(self, recipient, invoicedate, refunddate, invoicenum, invoiceamount, invoicevat, refundamount, refundvat, paymentmethod):
        self.title = "Refund of invoice {0}".format(invoicenum)
        self.recipient = recipient
        self.invoicedate = invoicedate
        self.refunddate = refunddate
        self.invoiceamount = invoiceamount
        self.invoicevat = invoicevat
        self.refundamount = refundamount
        self.refundvat = refundvat
        self.paymentmethod = paymentmethod

        super(BaseRefund, self).__init__(recipient)

    def save(self):
        self.draw_header()

        self.canvas.drawCentredString(cm(10.5), cm(19), "REFUND NOTE FOR INVOICE NUMBER {0}".format(self.invoicenum))

        tblpaid = [
            ["Amount paid"],
            ["Item", "Amount"],
            ["Amount", "{0:.2f} {1}".format(self.invoiceamount, settings.CURRENCY_SYMBOL)],
        ]
        tblrefunded = [
            ["Amount refunded"],
            ["Item", "Amount"],
            ["Amount", "{0:.2f} {1}".format(self.refundamount, settings.CURRENCY_SYMBOL)],
        ]
        if self.invoicevat:
            tblpaid.extend([
                ["VAT", "{0:.2f} {1}".format(self.invoicevat, settings.CURRENCY_SYMBOL)],
                ["", "{0:.2f} {1}".format(self.invoiceamount + self.invoicevat, settings.CURRENCY_SYMBOL)],
            ])
            tblrefunded.extend([
                ["VAT", "{0:.2f} {1}".format(self.refundvat, settings.CURRENCY_SYMBOL)],
                ["", "{0:.2f} {1}".format(self.refundamount + self.refundvat, settings.CURRENCY_SYMBOL)],
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

        t = Table(tblpaid, [cm(10.5), cm(2.5), cm(1.5), cm(2.5)])
        t.setStyle(TableStyle(style))
        w, h = t.wrapOn(self.canvas, cm(10), cm(10))
        t.drawOn(self.canvas, (self.canvas._pagesize[0] - w) / 2, cm(18) - h)

        t = Table(tblrefunded, [cm(10.5), cm(2.5), cm(1.5), cm(2.5)])
        t.setStyle(TableStyle(style))
        w, h = t.wrapOn(self.canvas, cm(10), cm(10))
        t.drawOn(self.canvas, (self.canvas._pagesize[0] - w) / 2, cm(18) - h * 2 - cm(1))

        self.canvas.drawCentredString(cm(10.5), cm(17.3) - h * 2 - cm(2), "This refund was issued {0}".format(self.refunddate.strftime("%B %d, %Y")))

        if self.paymentmethod:
            self.canvas.drawCentredString(cm(10.5), cm(17.3) - h * 2 - cm(3), "Refunded to the original form of payment: {0}.".format(self.paymentmethod))

        self.canvas.showPage()
        self.canvas.save()

        return self.pdfdata
