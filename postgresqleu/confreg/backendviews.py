from django.shortcuts import render, get_object_or_404
from django.db import transaction
from django import forms
from django.core import urlresolvers
from django.http import HttpResponseRedirect, Http404
from django.contrib.admin.utils import NestedObjects
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings

import urllib

from postgresqleu.util.middleware import RedirectException

from models import Conference, ConferenceRegistration
from models import RegistrationType, RegistrationClass

from backendforms import BackendConferenceForm, BackendRegistrationForm
from backendforms import BackendRegistrationTypeForm, BackendRegistrationClassForm
from backendforms import BackendRegistrationDayForm, BackendAdditionalOptionForm
from backendforms import BackendTrackForm, BackendRoomForm, BackendConferenceSessionForm
from backendforms import BackendConferenceSessionSlotForm, BackendVolunteerSlotForm
from backendforms import BackendFeedbackQuestionForm

def get_authenticated_conference(request, urlname):
	if not request.user.is_authenticated:
		raise RedirectException("{0}?{1}".format(settings.LOGIN_URL, urllib.urlencode({'next': request.build_absolute_uri()})))

	if request.user.is_superuser:
		return get_object_or_404(Conference, urlname=urlname)
	else:
		return get_object_or_404(Conference, urlname=urlname, administrators=request.user)

def backend_process_form(request, urlname, formclass, id, cancel_url='../', saved_url='../', allow_new=False, allow_delete=False, breadcrumbs=None, permissions_already_checked=False, conference=None, bypass_conference_filter=False):
	if not conference:
		conference = get_authenticated_conference(request, urlname)

	if not formclass.Meta.fields:
		raise Exception("This view only works if fields are explicitly listed")

	nopostprocess = False
	newformdata = None

	if allow_new and not id:
		if formclass.form_before_new:
			if request.method == 'POST' and '_validator' in request.POST:
				# This is a postback from the *actual* form
				print("Setting newformdata 1!")
				newformdata = request.POST['_newformdata']
				instance = formclass.Meta.model(conference=conference)
			else:
				# Postback to the first step create form
				newinfo = False
				if request.method == 'POST':
					# Making the new one!
					newform = formclass.form_before_new(request.POST)
					if newform.is_valid():
						newinfo = True
				else:
					newform = formclass.form_before_new()
				if not newinfo:
					return render(request, 'confreg/admin_backend_form.html', {
						'conference': conference,
						'form': newform,
						'what': 'New {0}'.format(formclass.Meta.model._meta.verbose_name),
						'cancelurl': cancel_url,
						'breadcrumbs': breadcrumbs,
					})
				instance = formclass.Meta.model(conference=conference)
				newformdata = newform.get_newform_data()
				nopostprocess = True
		else:
			# No special form_before_new, so just create an empty instance
			instance = formclass.Meta.model(conference=conference)
	else:
		if bypass_conference_filter:
			instance = get_object_or_404(formclass.Meta.model, pk=id)
		else:
			instance = get_object_or_404(formclass.Meta.model, pk=id, conference=conference)

	if request.method == 'POST' and not nopostprocess:
		extra_error=None
		if allow_delete and request.POST['submit'] == 'Delete':
			if instance.pk:
				# Are there any associated objects here, by any chance?
				collector=NestedObjects(using='default')
				collector.collect([instance,])
				to_delete = collector.nested()
				to_delete.remove(instance)
				if to_delete:
					pieces=[unicode(to_delete[0][n]) for n in range(0, min(5, len(to_delete[0]))) if not isinstance(to_delete[0][n], list)]
					extra_error=u"This {0} cannot be deleted. It would have resulted in the following other objects also being deleted: {1}".format(formclass.Meta.model._meta.verbose_name,u', '.join(pieces))
				else:
					messages.info(request, "{0} {1} deleted.".format(formclass.Meta.model._meta.verbose_name.capitalize(), instance))
					instance.delete()
					return HttpResponseRedirect(cancel_url)
			else:
				messages.warning(request, "New {0} not deleted, object was never saved.".format(formclass.Meta.model._meta.verbose_name.capitalize()))
				return HttpResponseRedirect(cancel_url)

		form = formclass(conference, instance=instance, data=request.POST, newformdata=newformdata)
		if extra_error:
			form.add_error(None, extra_error)

		if form.is_valid():
			# We don't want to use form.save(), because it actually saves all
			# fields on the model, including those we don't care about.
			# The savem2m model, however, *does* care about the lsited fields.
			# Consistency is overrated!
			with transaction.atomic():
				if allow_new and not instance.pk:
					form.save()
				form._save_m2m()
				form.instance.save(update_fields=[f for f in form.fields.keys() if not f in ('_validator', '_newformdata') and not isinstance(form[f].field, forms.ModelMultipleChoiceField)])
				return HttpResponseRedirect(saved_url)
	else:
		form = formclass(conference, instance=instance, newformdata=newformdata)

	if instance.id:
		adminurl = urlresolvers.reverse('admin:{0}_{1}_change'.format(instance._meta.app_label, instance._meta.model_name), args=(instance.id,))
	else:
		adminurl = None
	return render(request, 'confreg/admin_backend_form.html', {
		'conference': conference,
		'form': form,
		'what': formclass.Meta.model._meta.verbose_name,
		'cancelurl': cancel_url,
		'selectize_multiple_fields': formclass.selectize_multiple_fields,
		'breadcrumbs': breadcrumbs,
		'allow_delete': allow_delete and instance.pk,
		'adminurl': adminurl,
	})

def backend_list_editor(request, urlname, formclass, resturl, return_url='../', allow_new=False, allow_delete=False, conference=None):
	if not conference:
		conference = get_authenticated_conference(request, urlname)

	if resturl:
		resturl = resturl.rstrip('/')
	if resturl == '' or resturl == None:
		# Render the list of objects
		objects = formclass.Meta.model.objects.filter(conference=conference)
		values = [{'id': o.id, 'vals': [getattr(o, '_display_{0}'.format(f), getattr(o, f)) for f in formclass.list_fields]} for o in objects]
		return render(request, 'confreg/admin_backend_list.html', {
			'conference': conference,
			'values': values,
			'title': formclass.Meta.model._meta.verbose_name_plural.capitalize(),
			'singular_name': formclass.Meta.model._meta.verbose_name,
			'headers': [formclass.get_field_verbose_name(f) for f in formclass.list_fields],
			'return_url': return_url,
			'allow_new': allow_new,
			'allow_delete': allow_delete,
		})

	if allow_new and resturl=='new':
		# This one is more interesting...
		return backend_process_form(request,
									urlname,
									formclass,
									None,
									allow_new=True,
									allow_delete=allow_delete,
									breadcrumbs=[('../', formclass.Meta.model._meta.verbose_name_plural.capitalize()), ],
									conference=conference)

	# Is it an id?
	try:
		id = int(resturl)
	except ValueError:
		# No id. So we don't know. Fail.
		raise Http404()

	return backend_process_form(request,
								urlname,
								formclass,
								id,
								allow_delete=allow_delete,
								breadcrumbs=[('../', formclass.Meta.model._meta.verbose_name_plural.capitalize()), ],
								conference=conference)


#######################
# Simple editing views
#######################

def edit_conference(request, urlname):
	# Need to bypass the conference filter, since conference is not linked to
	# conference. However, the validation on urlname is already done, so there
	# is no way to access it without having the permissions in the first place.
	return backend_process_form(request,
								urlname,
								BackendConferenceForm,
								get_object_or_404(Conference, urlname=urlname).pk,
								bypass_conference_filter=True)

def edit_registration(request, urlname, regid):
	return backend_process_form(request,
								urlname,
								BackendRegistrationForm,
								regid)

def edit_regclasses(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendRegistrationClassForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_regtypes(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendRegistrationTypeForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_regdays(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendRegistrationDayForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_additionaloptions(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendAdditionalOptionForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_tracks(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendTrackForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_rooms(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendRoomForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_sessions(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendConferenceSessionForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_scheduleslots(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendConferenceSessionSlotForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_volunteerslots(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendVolunteerSlotForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)

def edit_feedbackquestions(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendFeedbackQuestionForm,
							   rest,
							   allow_new=True,
							   allow_delete=True)
