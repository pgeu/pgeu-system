#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render
from django import forms
from django.http import HttpResponse
from django.db.models import Q
from django.conf import settings

from datetime import timedelta
from collections import defaultdict
import copy

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm, mm

from models import Room, Track, RegistrationDay, ConferenceSession
from backendviews import get_authenticated_conference

def _get_pagesize(size, orient):
    so = (size, orient)
    if so == ('a4', 'p'):
        return A4
    if so == ('a4', 'l'):
        return landscape(A4)
    if so == ('a3', 'p'):
        return A3
    if so == ('a3', 'l'):
        return landscape(A3)
    raise Exception("Unknown papersize")

def _setup_canvas(pagesize, orientation):
    resp = HttpResponse(content_type='application/pdf')
    registerFont(TTFont('DejaVu Serif', "/usr/share/fonts/truetype/ttf-dejavu/DejaVuSerif.ttf"))
    ps = _get_pagesize(pagesize, orientation)
    (width, height) = ps
    canvas = Canvas(resp, pagesize=ps)
    canvas.setAuthor(settings.ORG_NAME)
    canvas._doc.info.producer = "{0} Confreg System".format(settings.ORG_SHORTNAME)

    return (width, height, canvas, resp)

# Build a linear PDF schedule for a single room only. Can do muptiple days, in which
# case each new day will cause a pagebreak.
def build_linear_pdf_schedule(conference, room, tracks, day, colored, pagesize, orientation, titledatefmt):
    q = Q(conference=conference, status=1, starttime__isnull=False, endtime__isnull=False)
    q = q & (Q(room=room) | Q(cross_schedule=True))
    q = q & (Q(track__in=tracks) | Q(track__isnull=True))
    if day:
        q = q & Q(starttime__range=(day.day, day.day + timedelta(days=1)))

    sessions = ConferenceSession.objects.select_related('track', 'room').filter(q).order_by('starttime')

    (width, height, canvas, resp) = _setup_canvas(pagesize, orientation)

    # Fetch and modify styles
    st_title = getSampleStyleSheet()['Normal']
    st_title.fontName = "DejaVu Serif"
    st_title.fontSize = 10
    st_title.spaceAfter = 8
    st_speakers = getSampleStyleSheet()['Normal']
    st_speakers.fontName = "DejaVu Serif"
    st_speakers.fontSize = 10
    st_speakers.spaceAfter = 8

    table_horiz_margin = 2*cm

    default_tbl_style = [
            ('VALIGN', (0,0), (-1, -1), 'TOP'),
            ('BOX', (0,0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0,0), (-1, -1), 0.5, colors.black),
            ('BOTTOMPADDING', (0,0), (-1, -1), 15),
        ]

    # Loop over days, creating one page for each day
    lastdate = None
    tbldata = []
    tblstyle = copy.copy(default_tbl_style)

    def _finalize_page():
        canvas.setFont("DejaVu Serif", 20)
        canvas.drawCentredString(width/2, height-2*cm, "%s - %s" % (room.roomname, lastdate.strftime(titledatefmt)))

        t = Table(tbldata, colWidths=[3*cm, width - 3*cm - 2*table_horiz_margin])
        t.setStyle(TableStyle(tblstyle))
        w,h = t.wrapOn(canvas, width, height)
        t.drawOn(canvas, table_horiz_margin, height-4*cm-h)
        canvas.showPage()

    for s in sessions:
        if s.starttime.date() != lastdate:
            if lastdate != None:
                # New page for a new day!
                _finalize_page()
            lastdate = s.starttime.date()
            tbldata = []
            tblstyle = copy.copy(default_tbl_style)
        tstr = Paragraph("%s - %s" % (s.starttime.strftime("%H:%M"), s.endtime.strftime("%H:%M")), st_title)
        if s.cross_schedule:
            # Just add a blank row for cross schedule things, so we get the time on there
            tbldata.extend([(tstr, '')])
        else:
            tbldata.extend([(tstr, (Paragraph(s.title, st_title), Paragraph("<i>%s</i>" % s.speaker_list, st_speakers)))])
            if colored and s.track and s.track.color:
                tblstyle.append(('BACKGROUND', (1,len(tbldata)-1), (1,len(tbldata)-1), s.track.color),)

    _finalize_page()
    canvas.save()

    return resp





def build_complete_pdf_schedule(conference, tracks, day, colored, pagesize, orientation, pagesperday, titledatefmt):
    pagesperday = int(pagesperday)

    q = Q(conference=conference, status=1, starttime__isnull=False, endtime__isnull=False)
    q = q & (Q(room__isnull=False) | Q(cross_schedule=True))
    q = q & (Q(track__in=tracks) | Q(track__isnull=True))
    if day:
        q = q & Q(starttime__range=(day.day, day.day + timedelta(days=1)))

    sessions = list(ConferenceSession.objects.select_related('track', 'room').filter(q).order_by('starttime', 'room__sortkey', 'room__roomname'))

    (width, height, canvas, resp) = _setup_canvas(pagesize, orientation)

    groupedbyday = defaultdict(dict)
    lastday = None
    for s in sessions:
        d = s.starttime.date()
        if lastday != d:
            # New day!
            groupedbyday[d] = {
                'first': s.starttime,
                'last': s.endtime,
                'sessions': []
                }
            lastday = d
        groupedbyday[d]['last'] = s.endtime
        groupedbyday[d]['sessions'].append(s)
    for k,v in groupedbyday.items():
        v['length'] = v['last']-v['first']
        v['rooms'] = set([s.room for s in v['sessions'] if s.room])

    timestampstyle = ParagraphStyle('timestampstyle')
    timestampstyle.fontName="DejaVu Serif"
    timestampstyle.fontSize = 8

    # Now build one page for each day
    for d in sorted(groupedbyday.keys()):
        dd = groupedbyday[d]

        usableheight = height - 2*2*cm - 1*cm
        usablewidth = width - 2*2*cm

        pagesessions=[]
        currentpagesessions=[]
        if pagesperday > 1:
            # >1 page per day, so we try to find the breakpoints. We do this by locating
            # cross-schedule sessions at appropriate times, and including those both on
            # the previous and the current schedule.
            secondsperpage = dd['length'].seconds / pagesperday

            cross_sessions = [s for s in dd['sessions'] if s.cross_schedule]

            breakpoints = []
            # For each breakpoint, find the closest one
            for p in range(1,pagesperday):
                breaktime = dd['first'] + timedelta(seconds=p * secondsperpage)
                breaksession = cross_sessions[min(range(len(cross_sessions)), key=lambda i: abs(cross_sessions[i].starttime-breaktime))]
                if not breaksession in breakpoints:
                    breakpoints.append(breaksession)

            for s in dd['sessions']:
                currentpagesessions.append(s)
                if s in breakpoints:
                    pagesessions.append(currentpagesessions)
                    # Make sure the breaking sessions itself is on both pages
                    currentpagesessions = [s,]
            pagesessions.append(currentpagesessions)
        else:
            # For a single page schedule, just add all sessions to the first page.
            pagesessions.append(dd['sessions'])

        # Calculate the vertical size once for all pages, to make sure we get the same size on
        # all pages even if the content is different. We do this by picking the *smallest* size
        # required for any page (start at usableheight just to be sure it will always get replaced)
        unitspersecond = usableheight
        for p in pagesessions:
            u = usableheight / (p[-1].endtime-p[0].starttime).seconds
            if u < unitspersecond:
                unitspersecond = u

        # Only on the first page in multipage schedules
        canvas.setFont("DejaVu Serif", 20)
        canvas.drawCentredString(width/2, height-2*cm, d.strftime(titledatefmt))

        roomcount = len(dd['rooms'])
        roomwidth = usablewidth / roomcount

        # Figure out font size for the room title. Use the biggest one that will still
        # fit within the boxes.
        roomtitlefontsize = 20
        for r in dd['rooms']:
            for fs in 16,14,12,10,8:
                fwidth = canvas.stringWidth(r.roomname, "DejaVu Serif", fs)
                if fwidth < roomwidth-4*mm:
                    # Width at this size is small enough to work, so use it
                    if fs < roomtitlefontsize:
                        roomtitlefontsize = fs
                    break
        canvas.setFont("DejaVu Serif", roomtitlefontsize)

        roompos = {}
        for r in sorted(dd['rooms'], key=lambda x: (x.sortkey, x.roomname)):
            canvas.rect(2*cm + len(roompos) * roomwidth, height-4*cm, roomwidth, 1*cm, stroke=1)
            canvas.drawCentredString(2*cm + len(roompos) * roomwidth + roomwidth / 2,
                                     height - 4*cm + (1*cm-roomtitlefontsize)/2,
                                     r.roomname)
            roompos[r] = len(roompos)

        for ps in pagesessions:
            pagelength = (ps[-1].endtime-ps[0].starttime).seconds
            first = ps[0].starttime

            canvas.rect(2*cm, height-pagelength*unitspersecond-4*cm, roomcount*roomwidth, pagelength*unitspersecond,stroke=1)
            for s in ps:
                if s.cross_schedule:
                    # Cross schedule rooms are very special...
                    s_left = 2*cm
                    thisroomwidth = roomcount * roomwidth
                else:
                    s_left = 2*cm + roompos[s.room] * roomwidth
                    thisroomwidth = roomwidth
                s_height = (s.endtime-s.starttime).seconds * unitspersecond
                s_top = height - (s.starttime-first).seconds * unitspersecond - s_height - 4*cm
                if colored:
                    if s.track and s.track.color:
                        canvas.setFillColor(s.track.color)
                    else:
                        canvas.setFillColor(colors.white)
                canvas.rect(s_left,s_top,thisroomwidth,s_height,stroke=1,fill=colored)

                timestampstr = "%s-%s" % (s.starttime.strftime("%H:%M"), s.endtime.strftime("%H:%M"))
                ts = Paragraph(timestampstr, timestampstyle)
                (tsaw, tsah) = ts.wrap(thisroomwidth-2*mm, timestampstyle.fontSize)
                ts.drawOn(canvas, s_left+1*mm, s_top+s_height-tsah-1*mm)


                if s_height - tsah*1.2 - 2*mm < tsah:
                    # This can never fit, since it's smaller than our font size!
                    # Instead, print as much as possible on the same row as the time
                    tswidth = canvas.stringWidth(timestampstr, "DejaVu Serif", 8)
                    title = s.title
                    trunc = ''
                    while title:
                        t = title + trunc
                        fwidth = canvas.stringWidth(t, "DejaVu Serif", 8)
                        if fwidth < thisroomwidth - tswidth - 2*mm:
                            # Fits now!
                            canvas.setFont("DejaVu Serif", 8)
                            p = Paragraph(t, timestampstyle)
                            (paw, pah) = p.wrap(thisroomwidth-tswidth-2*mm, timestampstyle.fontSize)
                            p.drawOn(canvas, s_left+1*mm+tswidth+1*mm, s_top+s_height-tsah-1*mm)
                            break
                        else:
                            title = title.rpartition(' ')[0]
                            trunc = '..'
                    continue
                try:
                    for includespeaker in (True, False):
                        title = s.title
                        while title:
                            for fs in (12,10,9,8):
                                sessionstyle = ParagraphStyle('sessionstyle')
                                sessionstyle.fontName="DejaVu Serif"
                                sessionstyle.fontSize = fs
                                speakersize = fs > 8 and 8 or fs - 1
                                if includespeaker:
                                    p = Paragraph(title + "<br/><font size=%s>%s</font>" % (speakersize, s.speaker_list), sessionstyle)
                                else:
                                    p = Paragraph(title, sessionstyle)

                                (aw, ah) = p.wrap(thisroomwidth-2*mm, s_height-tsah*1.2-2*mm)
                                if ah <= s_height-tsah*1.2-2*mm:
                                    # FIT!
                                    p.drawOn(canvas, s_left+1*mm, s_top+s_height-ah-tsah*1.2-1*mm)
                                    raise StopIteration
                            # Too big, so try to chop down the title and run again
                            # (this is assuming our titles are reasonable length, or we could be
                            # looping for a *very* long time)
                            title = "%s.." % title.rpartition(' ')[0]
                            if title == '..':
                                title = ''
                except StopIteration:
                    pass

            canvas.showPage()

    canvas.save()
    return resp

class PdfScheduleForm(forms.Form):
    room = forms.ModelChoiceField(label='Rooms to include', queryset=None, empty_label='(all rooms)', required=False,
                                  help_text="Selecting all rooms will print a full schedule with each session sized to it's length. Selecting a single room will print that rooms schedule in adaptive sized rows in a table.")
    day = forms.ModelChoiceField(label='Days to include', queryset=None, empty_label='(all days)', required=False)
    tracks = forms.ModelMultipleChoiceField(label='Tracks to include', queryset=None, required=True, help_text="Filter for some tracks. By default, all tracks are included.")
    colored = forms.BooleanField(label='Colored tracks', required=False)
    pagesize = forms.ChoiceField(label='Page size', choices=(('a4', 'A4'),('a3','A3')))
    orientation = forms.ChoiceField(label='Orientation', choices=(('p', 'Portrait'),('l', 'Landscape')))
    pagesperday = forms.ChoiceField(label='Pages per day', choices=((1,1),(2,2),(3,3)), help_text="Not used for per-room schedules. Page breaks happen only at cross-schedule sessions.")
    titledatefmt = forms.CharField(label='Title date format', help_text="strftime format specification used to print the date in the title of the first page for each day")

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference

        alltracks = Track.objects.filter(conference=conference).order_by('sortkey', 'trackname')
        kwargs['initial'] = {'titledatefmt': '%A, %b %d', 'tracks': alltracks}
        super(PdfScheduleForm, self).__init__(*args, **kwargs)
        self.fields['room'].queryset = Room.objects.filter(conference=conference)
        self.fields['day'].queryset = RegistrationDay.objects.filter(conference=conference)
        self.fields['tracks'].queryset = alltracks

def pdfschedule(request, confname):
    conference = get_authenticated_conference(request, confname)

    if request.method == "POST":
        form = PdfScheduleForm(conference, data=request.POST)
        if form.is_valid():
            if form.cleaned_data.has_key('room') and form.cleaned_data['room']:
                return build_linear_pdf_schedule(conference,
                                                 form.cleaned_data['room'],
                                                 form.cleaned_data['tracks'],
                                                 form.cleaned_data.has_key('day') and form.cleaned_data['day'],
                                                 form.cleaned_data.has_key('colored') and form.cleaned_data['colored'],
                                                 form.cleaned_data.has_key('pagesize') and form.cleaned_data['pagesize'],
                                                 form.cleaned_data.has_key('orientation') and form.cleaned_data['orientation'],
                                                 form.cleaned_data.has_key('titledatefmt') and form.cleaned_data['titledatefmt'],
                )
            else:
                return build_complete_pdf_schedule(conference,
                                                   form.cleaned_data['tracks'],
                                                   form.cleaned_data.has_key('day') and form.cleaned_data['day'],
                                                   form.cleaned_data.has_key('colored') and form.cleaned_data['colored'],
                                                   form.cleaned_data.has_key('pagesize') and form.cleaned_data['pagesize'],
                                                   form.cleaned_data.has_key('orientation') and form.cleaned_data['orientation'],
                                                   form.cleaned_data.has_key('pagesperday') and form.cleaned_data['pagesperday'],
                                                   form.cleaned_data.has_key('titledatefmt') and form.cleaned_data['titledatefmt'],
                )

        # Fall through and render the form again if it's not valid
    else:
        form = PdfScheduleForm(conference)

    return render(request, 'confreg/pdfschedule.html', {
        'conference': conference,
        'form': form,
        'helplink': 'schedule#pdf',
    })
