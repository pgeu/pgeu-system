from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db import connection

from postgresqleu.util.decorators import ssl_required

from models import Conference, ConferenceFeedbackQuestion, ConferenceFeedbackAnswer
from views import ConferenceContext

from collections import OrderedDict

def build_graphdata(question, key, options):
	optionhash = OrderedDict(zip(options, [0] * len(options)))
	for answer in ConferenceFeedbackAnswer.objects.filter(conference=question.conference, question=question).order_by(key).values(key).annotate(Count(key)):
		optionhash[answer[key]] = answer['%s__count' % key]
	return optionhash.iteritems()

def build_feedback_response(question):
	r = {'question': question.question, 'id': question.id, }
	confid=question.conference.id
	questionid=question.id
	if question.isfreetext:
		# This can actually be either freetext *or* graph!
		if question.textchoices:
			r['graphdata'] = build_graphdata(question, 'textanswer', question.textchoices.split(';'))
		else:
			r['textanswers'] = [a.textanswer for a in ConferenceFeedbackAnswer.objects.only('textanswer').filter(conference_id=confid, question_id=questionid).exclude(textanswer='')]
	else:
		# Numeric choices from 1-5
		r['graphdata'] = build_graphdata(question, 'rateanswer', range(0,6))
	return r

@ssl_required
@login_required
def feedback_report(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

	sections = []
	# Get the global conference feedback. Yes, this will be inefficient, but it will work
	currentsection = {}
	for q in ConferenceFeedbackQuestion.objects.filter(conference=conference).order_by('sortkey'):
		if q.newfieldset:
			if currentsection:
				sections.append(currentsection)
				currentsection = {}
			if not currentsection:
				# Either first row, or a new fieldset per above
				currentsection['title'] = q.newfieldset
				currentsection['questions'] = []
		currentsection['questions'].append(build_feedback_response(q))
	else:
		sections.append(currentsection)

	return render_to_response('confreg/conference_feedback.html', {
		'conference': conference,
		'feedback': sections,
	}, context_instance=ConferenceContext(request, conference))


def build_toplists(what, query):
	cursor = connection.cursor()
	for k in ('topic_importance', 'content_quality', 'speaker_knowledge', 'speaker_quality'):
		tl = {'title': '%s by %s' % (what, k.replace('_',' ').title())}
		cursor.execute(query.replace('{{key}}', k))
		tl['list'] = cursor.fetchall()
		yield tl

@ssl_required
@login_required
def feedback_sessions(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

	# Get all sessions that have actual comments on them
	cursor = connection.cursor()
	cursor.execute("SELECT s.title || ' (' || (SELECT string_agg(fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON css.speaker_id=spk.id WHERE css.conferencesession_id=s.id) || ')', conference_feedback FROM confreg_conferencesessionfeedback fb INNER JOIN confreg_conferencesession s ON fb.session_id=s.id WHERE s.conference_id=%s AND NOT conference_feedback='' ORDER BY 1,2" % (conference.id,))
	commented_sessions = cursor.fetchall()

	# Now for all of our fancy toplists
	# The django ORM just can't do this...
	minvotes = 10
	if request.method == 'POST':
		minvotes = int(request.POST['minvotes'])

	toplists = []

	# Start with top sessions
	toplists.extend(build_toplists('Sessions', "SELECT s.title || ' (' || (SELECT string_agg(fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON css.speaker_id=spk.id WHERE css.conferencesession_id=s.id) || ')', avg(fb.{{key}}), count(*), stddev(fb.{{key}}) FROM confreg_conferencesessionfeedback fb INNER JOIN confreg_conferencesession s ON fb.session_id=s.id WHERE s.conference_id=%s AND fb.{{key}}>0 GROUP BY s.id HAVING count(*)>%s ORDER BY 2 DESC" % (conference.id, minvotes)))

	# Now let's do the speakers
	toplists.extend(build_toplists('Speakers', "SELECT (SELECT string_agg(fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON css.speaker_id=spk.id WHERE css.conferencesession_id=s.id) AS speakername, avg(fb.{{key}}), count(*), stddev(fb.{{key}}) FROM confreg_conferencesessionfeedback fb INNER JOIN confreg_conferencesession s ON fb.session_id=s.id WHERE s.conference_id=%s AND fb.{{key}}>0 GROUP BY speakername HAVING count(*)>%s ORDER BY 2 DESC" % (conference.id, minvotes)))

	return render_to_response('confreg/conference_session_feedback.html', {
		'conference': conference,
		'toplists': toplists,
		'minvotes': minvotes,
		'commented_sessions': commented_sessions,
	}, context_instance=ConferenceContext(request, conference))
