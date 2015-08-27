from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, Http404
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.conf import settings

from cStringIO import StringIO
import difflib

from postgresqleu.util.decorators import ssl_required
from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.models import Conference, ConferenceRegistration
from postgresqleu.confreg.views import render_conference_response

from models import Wikipage, WikipageHistory, WikipageSubscriber
from forms import WikipageEditForm, WikipageAdminEditForm


@ssl_required
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

@ssl_required
@login_required
@transaction.commit_on_success
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

@ssl_required
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


@ssl_required
@login_required
@transaction.commit_on_success
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
				body = "{0} has modified the page '{1}' with the following changes\n\n\n{2}\n".format(reg.fullname, page.title, diff)
				send_simple_mail(conference.contactaddr,
								 conference.contactaddr,
								 subject,
								 body)
				body += "\n\nYou are receiving this message because you are subscribed to changes to\nthis page. To stop receiving notifications, please click\n{0}/events/register/{1}/wiki/{2}/sub/\n\n".format(settings.SITEBASE_SSL, conference.urlname, page.url)
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

@ssl_required
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

@ssl_required
@login_required
@transaction.commit_on_success
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
	}, RequestContext(request))

