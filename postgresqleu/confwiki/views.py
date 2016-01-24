from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, Http404
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.db import transaction, connection
from django.db.models import Q
from django.contrib import messages
from django.conf import settings

from datetime import datetime
from cStringIO import StringIO
import difflib

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.models import Conference, ConferenceRegistration
from postgresqleu.confreg.views import render_conference_response

from models import Wikipage, WikipageHistory, WikipageSubscriber
from forms import WikipageEditForm, WikipageAdminEditForm

from models import Signup, AttendeeSignup
from forms import SignupSubmitForm, SignupAdminEditForm

@login_required
def wikipage(request, confurl, wikiurl):
	conference = get_object_or_404(Conference, urlname=confurl)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user, payconfirmedat__isnull=False)
	pageQ = Q(publicview=True) | Q(viewer_attendee=reg) | Q(viewer_regtype=reg.regtype)
	pages = Wikipage.objects.filter(Q(conference=conference, url=wikiurl) & pageQ).distinct()
	if len(pages) != 1:
		raise Http404("Page not found")
	page = pages[0]

	is_subscribed = WikipageSubscriber.objects.filter(page=page, subscriber=reg).exists()

	# Ok, permissions to read. But does the user have permissions to
	# edit (so do we show the button?)
	editable = page.publicedit or page.editor_attendee.filter(id=reg.id).exists() or page.editor_regtype.filter(id=reg.regtype.id).exists()

	return render_conference_response(request, conference, 'confwiki/wikipage.html', {
		'page': page,
		'editable': editable,
		'is_subscribed': is_subscribed,
	})

@login_required
@transaction.atomic
def wikipage_subscribe(request, confurl, wikiurl):
	conference = get_object_or_404(Conference, urlname=confurl)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user, payconfirmedat__isnull=False)
	pageQ = Q(publicview=True) | Q(viewer_attendee=reg) | Q(viewer_regtype=reg.regtype)
	pages = Wikipage.objects.filter(Q(conference=conference, url=wikiurl) & pageQ).distinct()
	if len(pages) != 1:
		raise Http404("Page not found")
	page = pages[0]

	subs = WikipageSubscriber.objects.filter(page=page, subscriber=reg)
	if subs:
		subs.delete()
		messages.info(request, "{0} will no longer receive notifications for wiki page '{1}'.".format(reg.email, page.title))
	else:
		WikipageSubscriber(page=page, subscriber=reg).save()
		messages.info(request, "{0} will now receive notifications whenever wiki page '{1}' changes.".format(reg.email, page.title))

	return HttpResponseRedirect('../')

@login_required
def wikipage_history(request, confurl, wikiurl):
	conference = get_object_or_404(Conference, urlname=confurl)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user, payconfirmedat__isnull=False)
	pageQ = Q(publicview=True) | Q(viewer_attendee=reg) | Q(viewer_regtype=reg.regtype)
	pages = Wikipage.objects.filter(Q(conference=conference, url=wikiurl) & pageQ).distinct()
	if len(pages) != 1:
		raise Http404("Page not found")
	page = pages[0]

	fromid=toid=None

	if request.method == 'POST':
		# View a diff
		if not (request.POST.has_key('from') and request.POST.has_key('to')):
			messages.warning(request, "Must specify both source and target version")
			return HttpResponseRedirect('.')

		page_from = get_object_or_404(WikipageHistory, page=page, pk=request.POST['from'])
		fromid = page_from.id
		if request.POST['to'] != '-1':
			page_to = get_object_or_404(WikipageHistory, page=page, pk=request.POST['to'])
			toid = page_to.id
		else:
			page_to = page
			toid = None

		diff = "\n".join(difflib.unified_diff(page_from.contents.split('\r\n'),
											  page_to.contents.split('\r\n'),
											  fromfile='{0}'.format(page_from.publishedat),
											  tofile='{0}'.format(page_to.publishedat),
											  lineterm='',
											  ))
	else:
		diff = ''

	return render_conference_response(request, conference, 'confwiki/wikipage_history.html', {
		'page': page,
		'diff': diff,
		'fromid': fromid,
		'toid': toid,
	})


@login_required
@transaction.atomic
def wikipage_edit(request, confurl, wikiurl):
	conference = get_object_or_404(Conference, urlname=confurl)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user, payconfirmedat__isnull=False)
	pageQ = Q(publicedit=True) | Q(editor_attendee=reg) | Q(editor_regtype=reg.regtype)
	pages = Wikipage.objects.filter(Q(conference=conference, url=wikiurl) & pageQ).distinct()
	if len(pages) != 1:
		raise Http404("Page not found")
	page = pages[0]

	baseform = True
	preview = ''
	diff = ''

	if request.method == 'POST':
		form = WikipageEditForm(instance=page, data=request.POST)
		if form.is_valid():
			# If nothing at all has changed, just redirect back
			if not form.instance.diff:
				return HttpResponseRedirect('../')

			diff = "\n".join(difflib.unified_diff(form.instance.diff['contents'][0].split('\r\n'),
												  form.instance.diff['contents'][1].split('\r\n'), fromfile='before', tofile='after', lineterm=''))

			# If we have changes, check if the preview has been viewed
			# or if it needs to be shown.
			if request.POST['submit'] == 'Commit changes':
				# Generate a history entry first, and then save. Copy the
				# author from the current page (not changed yet), but get
				# the contents from the previous instance. Then we can
				# change the author on the new record.
				WikipageHistory(page=page, author=page.author, contents=form.instance.diff['contents'][0], publishedat=page.publishedat).save()
				page.author = reg
				page.save()

				# Send notifications to admin and to any subscribers
				subject = '[{0}] Wiki page {1} changed'.format(conference.conferencename, page.title)
				body = u"{0} has modified the page '{1}' with the following changes\n\n\n{2}\n".format(reg.fullname, page.title, diff)
				send_simple_mail(conference.contactaddr,
								 conference.contactaddr,
								 subject,
								 body)
				body += "\n\nYou are receiving this message because you are subscribed to changes to\nthis page. To stop receiving notifications, please click\n{0}/events/register/{1}/wiki/{2}/sub/\n\n".format(settings.SITEBASE, conference.urlname, page.url)
				for sub in WikipageSubscriber.objects.filter(page=page):
					send_simple_mail(conference.contactaddr,
									 reg.email,
									 subject,
									 body)

				return HttpResponseRedirect('../')
			elif request.POST['submit'] == 'Back to editing':
				# Fall through and render standard form
				pass
			else:
				# Else we clicked save
				baseform = False
				preview = form.cleaned_data['contents']
	else:
		form = WikipageEditForm(instance=page)

	return render_conference_response(request, conference, 'confwiki/wikipage_edit.html', {
		'page': page,
		'form': form,
		'baseform': baseform,
		'preview': preview,
		'diff': diff,
	})

@login_required
def admin(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	pages = Wikipage.objects.filter(conference=conference)

	return render_to_response('confwiki/admin.html', {
		'conference': conference,
		'pages': pages,
	}, RequestContext(request))

@login_required
@transaction.atomic
def admin_edit_page(request, urlname, pageid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	if pageid != 'new':
		page = get_object_or_404(Wikipage, conference=conference, pk=pageid)
	else:
		author = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)
		page = Wikipage(conference=conference, author=author)

	if request.method == 'POST':
		form = WikipageAdminEditForm(instance=page, data=request.POST)
		if form.is_valid():
			if pageid == 'new':
				form.save()
				send_simple_mail(conference.contactaddr,
								 conference.contactaddr,
								 "Wiki page '{0}' created by {1}".format(form.cleaned_data['url'], request.user),
								 "Title: {0}\nAuthor: {1}\nPublic view: {2}\nPublic edit: {3}\nViewer types: {4}\nEditor types: {5}\nViewer attendees: {6}\nEditor attendees: {7}\n\n".format(
									 form.cleaned_data['title'],
									 form.cleaned_data['author'].fullname,
									 form.cleaned_data['publicview'],
									 form.cleaned_data['publicedit'],
									 ", ".join([r.regtype for r in form.cleaned_data['viewer_regtype']]),
									 ", ".join([r.regtype for r in form.cleaned_data['editor_regtype']]),
									 ", ".join([r.fullname for r in form.cleaned_data['viewer_attendee']]),
									 ", ".join([r.fullname for r in form.cleaned_data['editor_attendee']]),
									 ))
			else:
				f = form.save(commit=False)
				form.save_m2m()
				s = StringIO()
				for k,v in f.diff.items():
					s.write("Changed {0} from {1} to {2}\n".format(k, v[0], v[1]))
				if s.tell() > 0:
					# Something changed, so generate audit email
					send_simple_mail(conference.contactaddr,
									 conference.contactaddr,
									 "Wiki page '{0}' edited by {1}".format(form.cleaned_data['url'], request.user),
									 s.getvalue())
				f.save()
			return HttpResponseRedirect('../')
	else:
		form = WikipageAdminEditForm(instance=page)

	return render_to_response('confwiki/admin_edit_form.html', {
		'conference': conference,
		'form': form,
		'page': page,
		'breadcrumbs': (('/events/admin/{0}/wiki/'.format(conference.urlname), 'Wiki'),),
	}, RequestContext(request))


@login_required
@transaction.atomic
def signup(request, urlname, signupid):
	conference = get_object_or_404(Conference, urlname=urlname)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user, payconfirmedat__isnull=False)
	signupQ = Q(public=True) | Q(attendees=reg) | Q(regtypes=reg.regtype)
	signups = Signup.objects.filter(Q(conference=conference, id=signupid) & signupQ).distinct()

	if len(signups) != 1:
		raise Http404("Page not found")
	signup = signups[0]
	attendee_signup = AttendeeSignup.objects.filter(signup=signup, attendee=reg)
	if len(attendee_signup) == 1:
		attendee_signup = attendee_signup[0]
	else:
		attendee_signup = None

	if signup.visible and attendee_signup:
		# Include the results
		cursor = connection.cursor()
		cursor.execute("SELECT firstname || ' ' || lastname FROM confreg_conferenceregistration r INNER JOIN confwiki_attendeesignup a ON a.attendee_id=r.id WHERE a.signup_id=%(signup)s AND r.payconfirmedat IS NOT NULL ORDER BY lastname, firstname", {
			'signup': signup.id,
		})
		current = [r[0] for r in cursor.fetchall()]
	else:
		current = None

	if signup.deadline and signup.deadline < datetime.now():
		# This one is closed
		return render_conference_response(request, conference, 'confwiki/signup.html', {
			'closed': True,
			'signup': signup,
			'attendee_signup': attendee_signup,
			'current': current,
		})

	# Signup is active, so build a form.
	if request.method == 'POST':
		form = SignupSubmitForm(signup, attendee_signup, data=request.POST)
		if form.is_valid():
			if form.cleaned_data['choice'] == '':
				# Remove instead!
				if attendee_signup:
					attendee_signup.delete()
					messages.info(request, "Your response has been deleted.")
				# If it did not exist, don't bother deleting it
			else:
				# Store an actual response
				if attendee_signup:
					attendee_signup.choice = form.cleaned_data['choice']
				else:
					attendee_signup = AttendeeSignup(attendee=reg,
													 signup=signup,
													 choice=form.cleaned_data['choice'])
				attendee_signup.save()
				messages.info(request, "Your response has been stored. Thank you!")

			return HttpResponseRedirect('../../')
	else:
		form = SignupSubmitForm(signup, attendee_signup)

	return render_conference_response(request, conference, 'confwiki/signup.html', {
		'closed': False,
		'signup': signup,
		'attendee_signup': attendee_signup,
		'current': current,
		'form': form,
	})

@login_required
def signup_admin(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	signups = Signup.objects.filter(conference=conference)

	return render_to_response('confwiki/signup_admin.html', {
		'conference': conference,
		'signups': signups,
	}, RequestContext(request))

@login_required
@transaction.atomic
def signup_admin_edit(request, urlname, signupid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	if signupid != 'new':
		signup = get_object_or_404(Signup, conference=conference, pk=signupid)
		# There can be results, so calculate them. We want both a list and
		# a summary.
		results = {}
		cursor = connection.cursor()
		cursor.execute("WITH t AS (SELECT choice, count(*) AS num FROM confwiki_attendeesignup WHERE signup_id=%(signup)s GROUP BY choice) SELECT choice, num, CAST(num*100*4/sum(num) OVER () AS integer) FROM t ORDER BY 2 DESC", {
			'signup': signup.id,
		})
		results['summary'] = [dict(zip(['choice', 'num', 'percentwidth'], r)) for r in cursor.fetchall()]
		cursor.execute("SELECT firstname || ' ' || lastname,choice,saved FROM confreg_conferenceregistration r INNER JOIN confwiki_attendeesignup s ON r.id=s.attendee_id WHERE s.signup_id=%(signup)s ORDER BY saved", {
			'signup': signup.id,
		})
		results['details'] = [dict(zip(['name', 'choice', 'when'], r)) for r in cursor.fetchall()]

		# If we have a limited number of attendees, then we can generate
		# a list of pending users. We don't even try if it's set for public.
		if not signup.public:
			cursor.execute("SELECT firstname || ' ' || lastname FROM confreg_conferenceregistration r WHERE payconfirmedat IS NOT NULL AND (regtype_id IN (SELECT registrationtype_id FROM confwiki_signup_regtypes srt WHERE srt.signup_id=%(signup)s) OR id IN (SELECT conferenceregistration_id FROM confwiki_signup_attendees WHERE signup_id=%(signup)s)) AND id NOT IN (SELECT attendee_id FROM confwiki_attendeesignup WHERE signup_id=%(signup)s) ORDER BY lastname, firstname", {
				'signup': signup.id,
			})
			results['awaiting'] = [dict(zip(['name', ], r)) for r in cursor.fetchall()]
	else:
		author = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)
		signup = Signup(conference=conference, author=author)
		results = None

	if request.method == 'POST':
		form = SignupAdminEditForm(instance=signup, data=request.POST)
		if form.is_valid():
			# We don't bother with diffs here as the only one who can
			# edit things are admins anyway.
			form.save()
			return HttpResponseRedirect('../')
	else:
		form = SignupAdminEditForm(instance=signup)

	return render_to_response('confwiki/signup_admin_edit_form.html', {
		'conference': conference,
		'form': form,
		'signup': signup,
		'results': results,
		'breadcrumbs': (('/events/admin/{0}/signups/'.format(conference.urlname), 'Signups'),),
	}, RequestContext(request))
