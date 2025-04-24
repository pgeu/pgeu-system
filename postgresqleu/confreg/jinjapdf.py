#!/usr/bin/env python3

import json
import os.path
import argparse
import sys
import re
import operator

from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from PIL import Image

import jinja2
import jinja2.sandbox

try:
    import postgresqleu.confreg.contextutil as contextutil
except ImportError:
    import contextutil

alignments = {
    'left': TA_LEFT,
    'center': TA_CENTER,
    'right': TA_RIGHT,
}


def get_color(col):
    if isinstance(col, str):
        return colors.getAllNamedColors().get(col)
    elif isinstance(col, list):
        return colors.Color(*[x / 255.0 for x in col])
    else:
        raise Exception("Unknown color definition type")


def getmm(struct, key):
    return struct[key] * mm


class JinjaFlowable(Flowable):
    def __init__(self, js, imgpath):
        self.js = js
        self.imgpath = imgpath
        self.width = getmm(js, 'width')
        self.height = getmm(js, 'height')
        self.fontname = self.js.get('fontname', 'DejaVu Serif')
        if self.js.get('center', False):
            self.hAlign = 'CENTER'

    def draw(self):
        if self.js.get('border', False):
            self.canv.rect(0, 0, self.width, self.height)

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

    def draw_circle(self, o):
        stroke = 0
        fill = 0
        if 'fill' in o:
            self.canv.setFillColor(get_color(o['fill']))
            fill = 1
        if 'stroke' in o and o['stroke'] is not False:
            stroke = 1
            if o['stroke'] is True or o['stroke'] == '1':
                self.canv.setStrokeColorRGB(0, 0, 0)
            else:
                self.canv.setStrokeColor(get_color(o['stroke']))
        self.canv.circle(getmm(o, 'x'),
                         self.height - getmm(o, 'y') - getmm(o, 'radius'),
                         getmm(o, 'radius'),
                         stroke=stroke,
                         fill=fill)

    def draw_box(self, o):
        stroke = 0
        fill = 0
        if 'fill' in o:
            self.canv.setFillColor(get_color(o['fill']))
            fill = 1
        if 'stroke' in o and o['stroke'] is not False:
            stroke = 1
            if o['stroke'] is True or o['stroke'] == '1':
                self.canv.setStrokeColorRGB(0, 0, 0)
            else:
                self.canv.setStrokeColor(get_color(o['stroke']))
        self.canv.rect(getmm(o, 'x'),
                       self.calc_y(o),
                       getmm(o, 'width'),
                       getmm(o, 'height'),
                       stroke=stroke,
                       fill=fill)

    def draw_line(self, o):
        if 'x2' in o and 'y2' in o:
            self.canv.line(getmm(o, 'x'),
                           self.height - getmm(o, 'y'),
                           getmm(o, 'x2'),
                           self.height - getmm(o, 'y2'))
        elif 'width' in o and 'height' in o:
            # Draw a line between the corners of a rectangle
            self.canv.line(getmm(o, 'x'),
                           self.calc_y(o),
                           getmm(o, 'x') + getmm(o, 'width'),
                           self.calc_y(o) + getmm(o, 'height'))
        else:
            raise Exception("Must specify x2/y2 or width/height")

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

    def draw_qrimage(self, o):
        s = o.get('qrcontent')
        if not s:
            return
        if len(s) < 20:
            ver = 1
        elif len(s) < 38:
            ver = 2
        elif len(s) < 61:
            ver = 3
        elif len(s) < 90:
            ver = 4
        elif len(s) < 122:
            ver = 5
        elif len(s) < 154:
            ver = 6
        else:
            raise Exception("String too long for QR encode")

        try:
            import qrcode

            qrimage = qrcode.make(s, version=ver, border=0)
        except ImportError:
            raise
            try:
                import qrencode
                (ver, size, qrimage) = qrencode.encode(s, version=ver, level=qrencode.QR_ECLEVEL_M)
            except ImportError:
                o2 = o.copy()
                o2['stroke'] = True
                o2['text'] = "qrencode library\nnot found"
                self.draw_box(o2)
                self.draw_paragraph(o2)
                return

        if qrimage.size[0] != 500:
            if qrimage.size[0] < 500:
                size = (500 // qrimage.size[0]) * qrimage.size[0]
            else:
                size = qrimage.size[0] // (qrimage.size[0] // 500 + 1)
            qrimage = qrimage.resize((size, size), Image.NEAREST)

        self.canv.drawImage(ImageReader(qrimage),
                            getmm(o, 'x'),
                            self.calc_y(o),
                            getmm(o, 'width'),
                            getmm(o, 'height'),
                            o.get('mask', 'auto'),
                            preserveAspectRatio=True,
        )

    def draw_paragraph(self, o):
        # Attempt to draw a paragraph that can dynamically change the font size
        # as necessary.
        fontname = o.get('fontname', self.fontname)
        if o.get('bold', False):
            fontname += ' Bold'
        if o.get('italic', False):
            fontname += ' Italic'
        if o.get('extralight', False):
            fontname += ' ExtraLight'
        lines = o['text'].splitlines()

        if len(lines) == 0:
            # Don't try to draw empty lines
            return

        # Max height is total height divided by lines divided by 1.2 since
        # we multiply the leading value with 1.2 later
        maxsize = o.get('maxsize', None)
        maxfont_height = int((getmm(o, 'height') // len(lines)) / 1.2)
        if maxsize:
            maxfontsize = min(maxsize, maxfont_height)
        else:
            maxfontsize = maxfont_height
        for fontsize in range(4, maxfontsize):
            maxwidth = max([self.canv.stringWidth(line, fontname, fontsize) for line in lines])
            if maxwidth > getmm(o, 'width'):
                fontsize -= 1
                break

        if o.get('verticalcenter', False):
            yoffset = (getmm(o, 'height') - (len(lines) * fontsize)) // 2
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
        p.drawOn(self.canv, getmm(o, 'x'), self.calc_y(o) + getmm(o, 'height') - actualheight - yoffset)


def escapejson_filter(v):
    # Dumping a string/unicode to json will add double quotes at beginning and end. Strip
    # those, but only one if there is more than one.
    return re.sub(r'^"|"$', '', json.dumps(v))


def test_inlist(v, thelist):
    return v in thelist


class JinjaRenderer(object):
    def __init__(self, rootdir, templatefile, fonts, debug=False, systemroot=None, orientation='portrait', pagesize='A4'):
        if rootdir:
            self.templatedir = os.path.join(rootdir, 'templates')
        else:
            self.templatedir = None

        self.pagesize = LETTER if pagesize == 'letter' else A4
        if orientation != 'portrait':
            self.pagesize = landscape(self.pagesize)

        self.debug = debug

        self.border = self.pagebreaks = False

        for font, fontfile in fonts:
            registerFont(TTFont(font, fontfile))

        if self.templatedir and os.path.exists(os.path.join(self.templatedir, templatefile)):
            template = os.path.join(self.templatedir, templatefile)
        elif systemroot and os.path.exists(os.path.join(systemroot, 'confreg/', templatefile)):
            template = os.path.join(systemroot, 'confreg/', templatefile)
        else:
            raise Exception("{0} not found for conference".format(templatefile))

        with open(template) as f:
            env = jinja2.sandbox.SandboxedEnvironment()
            env.filters.update({
                'escapejson': escapejson_filter,
                'yesno': lambda b, v: v.split(',')[not b],
            })
            env.tests.update({
                'inlist': test_inlist,
                'equalto': operator.eq,
            })
            self.template = env.from_string(f.read())

        if rootdir:
            self.context = contextutil.load_base_context(rootdir)
            contextutil.update_with_override_context(self.context, rootdir)
        else:
            self.context = {}

        if rootdir:
            self.staticdir = os.path.join(rootdir, 'static')
            if not os.path.isdir(self.staticdir):
                if debug:
                    print("Static directory {0} does not exist, ignoring.".format(self.staticdir))
                self.staticdir = None
        else:
            self.staticdir = None

        self.story = []

    def add_to_story(self, ctx):
        ctx.update(self.context)
        s = self.template.render(**ctx)
        try:
            js = json.loads(s)
        except ValueError as e:
            if self.debug:
                print("JSON parse failed. Template output:")
                print(s)
                print("------------------------")
                print("JSON parse failed: %s" % e)
                print("see template output above.")
                sys.exit(1)
            else:
                raise Exception("JSON parse failed.")

        if 'border' not in js:
            js['border'] = self.border
        self.story.append(JinjaFlowable(js, self.staticdir))

        if 'forcebreaks' not in js:
            js['forcebreaks'] = self.pagebreaks
        if js.get('forcebreaks', False):
            self.story.append(PageBreak())

    def render(self, output):
        doc = SimpleDocTemplate(output, pagesize=self.pagesize, leftMargin=10 * mm, topMargin=5 * mm, rightMargin=10 * mm, bottomMargin=5 * mm)
        doc.build(self.story)


class JinjaBadgeRenderer(JinjaRenderer):
    def __init__(self, rootdir, fonts, debug=False, border=False, pagebreaks=False, systemroot=None, orientation='portrait', pagesize='A4'):
        super(JinjaBadgeRenderer, self).__init__(rootdir, 'badge.json', fonts, debug=debug, systemroot=systemroot, orientation=orientation, pagesize=pagesize)

        self.border = border
        self.pagebreaks = pagebreaks

    def add_badge(self, reg, conference):
        self.add_to_story({
            'reg': reg,
            'conference': conference,
        })


class JinjaTicketRenderer(JinjaRenderer):
    def __init__(self, rootdir, fonts, debug=False, systemroot=None):
        super(JinjaTicketRenderer, self).__init__(rootdir, 'ticket.json', fonts, debug=debug, systemroot=systemroot)

    def add_reg(self, reg, conference):
        self.add_to_story({
            'reg': reg,
            'conference': conference,
        })


# Render badges from within the website scope, meaning we have access to the
# django objects here.
def render_jinja_badges(conference, fonts, registrations, output, border, pagebreaks, orientation='portrait', pagesize='A4'):
    renderer = JinjaBadgeRenderer(conference.jinjadir, fonts, border=border, pagebreaks=pagebreaks, orientation=orientation, pagesize=pagesize)

    for reg in registrations:
        renderer.add_badge(reg, conference.safe_export())

    renderer.render(output)


def render_jinja_ticket(registration, output, systemroot, fonts):
    renderer = JinjaTicketRenderer(registration.conference.jinjadir, fonts, systemroot=systemroot)
    renderer.add_reg(registration.safe_export(), registration.conference.safe_export())
    renderer.render(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Render jinja based badges and tickets')
    parser.add_argument('what', choices=['badge', 'ticket', ], help='What to render')
    parser.add_argument('repopath', type=str, help='Template repository directory')
    parser.add_argument('attendeelist', type=str, help='JSON file with attendee list')
    parser.add_argument('outputfile', type=str, help='Name of output PDF file')
    parser.add_argument('--confjson', type=str, help='JSON representing conference')
    parser.add_argument('--borders', action='store_true', help='Enable borders on written file')
    parser.add_argument('--pagebreaks', action='store_true', help='Enable pagebreaks on written file')
    parser.add_argument('--fontroot', type=str, help='fontroot for dejavu fonts')
    parser.add_argument('--font', type=str, nargs=1, action='append', help='<font name>:<font path>')

    args = parser.parse_args()

    if args.confjson:
        with open(args.confjson) as f:
            conference = json.load(f)
    else:
        conference = {}

    with open(args.attendeelist) as f:
        a = json.load(f)

    fonts = [
        ('DejaVu Serif', '{}/DejaVuSerif.ttf'.format(args.fontroot)),
        ('DejaVu Serif Italic', '{}/DejaVuSerif-Italic.ttf'.format(args.fontroot)),
        ('DejaVu Serif Bold', '{}/DejaVuSerif-Bold.ttf'.format(args.fontroot)),
        ('DejaVu Serif Bold Italic', '{}/DejaVuSerif-BoldItalic.ttf'.format(args.fontroot)),

        ('DejaVu Serif Condensed', '{}/DejaVuSerifCondensed.ttf'.format(args.fontroot)),
        ('DejaVu Serif Condensed Italic', '{}/DejaVuSerifCondensed-Italic.ttf'.format(args.fontroot)),
        ('DejaVu Serif Condensed Bold', '{}/DejaVuSerifCondensed-Bold.ttf'.format(args.fontroot)),
        ('DejaVu Serif Condensed Bold Italic', '{}/DejaVuSerifCondensed-BoldItalic.ttf'.format(args.fontroot)),

        ('DejaVu Sans', '{}/DejaVuSans.ttf'.format(args.fontroot)),
        ('DejaVu Sans Italic', '{}/DejaVuSans-Oblique.ttf'.format(args.fontroot)),
        ('DejaVu Sans Bold', '{}/DejaVuSans-Bold.ttf'.format(args.fontroot)),
        ('DejaVu Sans Bold Italic', '{}/DejaVuSans-BoldOblique.ttf'.format(args.fontroot)),
        ('DejaVu Sans ExtraLight', '{}/DejaVuSans-ExtraLight.ttf'.format(args.fontroot)),

        ('DejaVu Sans Condensed', '{}/DejaVuSansCondensed.ttf'.format(args.fontroot)),
        ('DejaVu Sans Condensed Italic', '{}/DejaVuSansCondensed-Oblique.ttf'.format(args.fontroot)),
        ('DejaVu Sans Condensed Bold', '{}/DejaVuSansCondensed-Bold.ttf'.format(args.fontroot)),
        ('DejaVu Sans Condensed Bold Italic', '{}/DejaVuSansCondensed-BoldOblique.ttf'.format(args.fontroot)),

        ('DejaVu Sans Mono', '{}/DejaVuSansMono.ttf'.format(args.fontroot)),
        ('DejaVu Sans Mono Italic', '{}/DejaVuSansMono-Oblique.ttf'.format(args.fontroot)),
        ('DejaVu Sans Mono Bold', '{}/DejaVuSansMono-Bold.ttf'.format(args.fontroot)),
        ('DejaVu Sans Mono Bold Italic', '{}/DejaVuSansMono-BoldOblique.ttf'.format(args.fontroot)),
    ]

    if args.font:
        for font in args.font:
            fonts.extend([f.split(':') for f in font])

    if args.what == 'badge':
        renderer = JinjaBadgeRenderer(args.repopath, fonts, debug=True, border=args.borders, pagebreaks=args.pagebreaks)
        for reg in a:
            renderer.add_badge(reg, conference)
    else:
        renderer = JinjaTicketRenderer(args.repopath, fonts, debug=True)
        renderer.add_reg(a[0], conference)

    with open(args.outputfile, 'wb') as output:
        renderer.render(output)
