from django.shortcuts import render
from django.db.models import Count
from django.db import connection

from .models import ConferenceFeedbackAnswer
from postgresqleu.confreg.util import get_authenticated_conference
from postgresqleu.util.request import get_int_or_error

from collections import OrderedDict


def build_graphdata(answers, options):
    optionhash = OrderedDict(list(zip(options, [0] * len(options))))
    if answers:
        for a in answers:
            optionhash[a] += 1
    return iter(optionhash.items())


def feedback_report(request, confname):
    conference = get_authenticated_conference(request, confname)

    sections = []
    # Get the global conference feedback. Actually pusing down the counting of options would
    # make this more efficient, but at least we're down to a single query now.
    curs = connection.cursor()
    curs.execute(
        """SELECT q.id, q.newfieldset, q.question, q.isfreetext, q.textchoices,
 array_agg(a.textanswer) FILTER (WHERE a.textanswer != '') AS textanswers,
 array_agg(a.rateanswer) FILTER (WHERE a.rateanswer IS NOT NULL) AS rateanswers
FROM confreg_conferencefeedbackquestion q
LEFT JOIN confreg_conferencefeedbackanswer a ON a.question_id=q.id
WHERE q.conference_id=%(confid)s
GROUP BY q.id
ORDER BY sortkey""", {
            'confid': conference.id,
        })

    currentsection = {}
    for questionid, newfieldset, question, isfreetext, textchoices, textanswers, rateanswers in curs.fetchall():
        if newfieldset:
            if currentsection:
                sections.append(currentsection)
                currentsection = {}
            if not currentsection:
                # Either first row, or a new fieldset per above
                currentsection['title'] = newfieldset
                currentsection['questions'] = []

        r = {
            'id': questionid,
            'question': question,
        }
        if isfreetext:
            if textchoices:
                # This is actually a set of choices, even if freetext is set
                r['graphdata'] = build_graphdata(textanswers, textchoices.split(';'))
            else:
                r['textanswers'] = textanswers
        else:
            r['graphdata'] = build_graphdata(rateanswers, list(range(0, 6)))

        if 'questions' in currentsection:
            currentsection['questions'].append(r)
        else:
            currentsection['questions'] = [r, ]
    else:
        sections.append(currentsection)

    return render(request, 'confreg/admin_conference_feedback.html', {
        'conference': conference,
        'numresponses': ConferenceFeedbackAnswer.objects.filter(conference=conference).aggregate(Count('attendee', distinct=True))['attendee__count'],
        'feedback': sections,
        'helplink': 'feedback',
    })


def build_toplists(what, query):
    cursor = connection.cursor()
    for k in ('topic_importance', 'content_quality', 'speaker_knowledge', 'speaker_quality'):
        tl = {'title': '%s by %s' % (what, k.replace('_', ' ').title())}
        cursor.execute(query.replace('{{key}}', k))
        tl['list'] = cursor.fetchall()
        yield tl


def feedback_sessions(request, confname):
    conference = get_authenticated_conference(request, confname)

    # Get all sessions that have actual comments on them
    cursor = connection.cursor()
    cursor.execute("SELECT concat(s.title, ' (' || (SELECT string_agg(fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON css.speaker_id=spk.id WHERE css.conferencesession_id=s.id) || ')'), conference_feedback FROM confreg_conferencesessionfeedback fb INNER JOIN confreg_conferencesession s ON fb.session_id=s.id WHERE s.conference_id=%s AND NOT conference_feedback='' ORDER BY 1,2" % (conference.id,))
    commented_sessions = cursor.fetchall()

    # Now for all of our fancy toplists
    # The django ORM just can't do this...
    minvotes = 10
    if request.method == 'POST':
        minvotes = get_int_or_error(request.POST, 'minvotes')

    toplists = []

    # Start with top sessions
    toplists.extend(build_toplists('Sessions', "SELECT s.title || ' (' || (SELECT string_agg(fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON css.speaker_id=spk.id WHERE css.conferencesession_id=s.id) || ')', avg(fb.{{key}}), count(*), stddev(fb.{{key}}) FROM confreg_conferencesessionfeedback fb INNER JOIN confreg_conferencesession s ON fb.session_id=s.id WHERE s.conference_id=%s AND fb.{{key}}>0 GROUP BY s.id HAVING count(*)>=%s ORDER BY 2 DESC" % (conference.id, minvotes)))

    # Now let's do the speakers
    toplists.extend(build_toplists('Speakers', "SELECT (SELECT string_agg(fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON css.speaker_id=spk.id WHERE css.conferencesession_id=s.id) AS speakername, avg(fb.{{key}}), count(*), stddev(fb.{{key}}) FROM confreg_conferencesessionfeedback fb INNER JOIN confreg_conferencesession s ON fb.session_id=s.id WHERE s.conference_id=%s AND fb.{{key}}>0 GROUP BY speakername HAVING count(*)>=%s ORDER BY 2 DESC" % (conference.id, minvotes)))

    return render(request, 'confreg/admin_session_feedback.html', {
        'conference': conference,
        'toplists': toplists,
        'minvotes': minvotes,
        'commented_sessions': commented_sessions,
        'breadcrumbs': (('/events/admin/{0}/reports/feedback/'.format(conference.urlname), 'Feedback'), ),
        'helplink': 'feedback',
    })
