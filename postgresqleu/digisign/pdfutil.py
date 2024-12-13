import io
import itertools

from reportlab.pdfgen.canvas import Canvas

from postgresqleu.util.reporttools import cm


def fill_pdf_fields(pdf, available_fields, fielddata):
    import fitz

    if 'fields' in fielddata:
        pagefields = {int(k): list(v) for k, v in itertools.groupby(fielddata['fields'], lambda x: x['page'])}
    else:
        pagefields = {}

    pdf = fitz.open('pdf', bytes(pdf))
    for pagenum, page in enumerate(pdf.pages()):
        if pagenum in pagefields:
            for f in pagefields[pagenum]:
                # Location in the json is top-left corner, but we want bottom-left for the
                # PDF. So we add the size of the font in points, which is turned into pixels
                # by multiplying by 96/72.
                p = fitz.Point(
                    f['x'],
                    f['y'] + fielddata['fontsize'] * 96 / 72,
                )

                # Preview with the field title
                txt = None
                for fieldname, fieldtext in available_fields:
                    if not fieldname.startswith('static:'):
                        break
                    if fieldname == f['field']:
                        txt = fieldtext
                        break
                else:
                    txt = ""

                if txt:
                    if fitz.version[0] > "1.19":
                        page.insert_text(p, txt, fontname='Courier-Bold', fontsize=fielddata['fontsize'])
                    else:
                        page.insertText(p, txt, fontname='Courier-Bold', fontsize=fielddata['fontsize'])

    return pdf.write()


def pdf_watermark_preview(pdfdata):
    try:
        import fitz
    except ImportError:
        # Just return without watermark
        return pdfdata

    wmio = io.BytesIO()
    wmcanvas = Canvas(wmio)
    wmcanvas.rotate(45)
    for y in -5, 0, 5, 10, 15:
        t = wmcanvas.beginText()
        t.setTextOrigin(cm(6), cm(y))
        t.setFont("Times-Roman", 100)
        t.setFillColorRGB(0.9, 0.9, 0.9)
        t.textLine("PREVIEW PREVIEW")
        wmcanvas.drawText(t)
    wmcanvas.rotate(-45)
    wmcanvas.save()

    wmio.seek(0)
    wmpdf = fitz.open('pdf', wmio)
    wmpixmap = next(wmpdf.pages()).getPixmap()

    pdf = fitz.open('pdf', pdfdata)
    for pagenum, page in enumerate(pdf.pages()):
        if fitz.version[0] > "1.19":
            page.insert_image(page.bound(), pixmap=wmpixmap, overlay=False)
        else:
            page.insertImage(page.bound(), pixmap=wmpixmap, overlay=False)

    return pdf.write()
