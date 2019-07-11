from django.core.exceptions import PermissionDenied
from django.db import transaction
from django import forms
from django.shortcuts import render, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib.admin.utils import NestedObjects
from django.contrib import messages

from postgresqleu.util.lists import flatten_list
from postgresqleu.confreg.util import get_authenticated_conference
from postgresqleu.confreg.backendforms import BackendCopySelectConferenceForm


def backend_process_form(request, urlname, formclass, id, cancel_url='../', saved_url='../', allow_new=True, allow_delete=True, breadcrumbs=None, permissions_already_checked=False, conference=None, bypass_conference_filter=False, instancemaker=None, deleted_url=None, topadmin=None):
    if not conference and not bypass_conference_filter:
        conference = get_authenticated_conference(request, urlname)

    if not formclass.Meta.fields:
        raise Exception("This view only works if fields are explicitly listed")

    if request.GET.get('fieldpreview', ''):
        f = request.GET.get('fieldpreview')
        if f not in formclass.dynamic_preview_fields:
            raise Http404()

        try:
            return HttpResponse(formclass.get_dynamic_preview(f, request.GET.get('previewval', ''), id), content_type='text/plain')
        except Exception:
            return HttpResponse('', content_type='text/plain')

    nopostprocess = False
    newformdata = None

    if not deleted_url:
        deleted_url = cancel_url

    if not instancemaker:
        if conference:
            instancemaker = lambda: formclass.Meta.model(conference=conference)
        else:
            instancemaker = lambda: formclass.Meta.model()

    if topadmin:
        basetemplate = 'adm/admin_base.html'
    else:
        basetemplate = 'confreg/confadmin_base.html'

    if allow_new and not id:
        if formclass.form_before_new:
            if request.method == 'POST' and '_validator' in request.POST:
                # This is a postback from the *actual* form
                newformdata = request.POST['_newformdata']
                instance = instancemaker()
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
                        'basetemplate': basetemplate,
                        'topadmin': topadmin,
                        'form': newform,
                        'whatverb': 'Create new',
                        'what': formclass.Meta.model._meta.verbose_name,
                        'savebutton': 'Create',
                        'cancelurl': cancel_url,
                        'helplink': newform.helplink,
                        'breadcrumbs': breadcrumbs,
                    })
                instance = instancemaker()
                newformdata = newform.get_newform_data()
                nopostprocess = True
        else:
            # No special form_before_new, so just create an empty instance
            instance = instancemaker()

        # Set initial values on newly created instance, if any are set
        for k, v in list(formclass.get_initial().items()):
            setattr(instance, k, v)
    else:
        if bypass_conference_filter:
            instance = get_object_or_404(formclass.Meta.model, pk=id)
        else:
            if hasattr(formclass.Meta, 'conference_queryset'):
                try:
                    instance = formclass.Meta.conference_queryset(conference).get(pk=id)
                except formclass.Meta.model.DoesNotExist:
                    raise Http404()
            else:
                instance = get_object_or_404(formclass.Meta.model, pk=id, conference=conference)

    if request.method == 'GET' and request.GET.get('validate', '') == '1':
        if not id:
            return HttpResponse("Record not saved, cannot preview", content_type='text/plain')
        else:
            try:
                return HttpResponse(formclass.validate_data_for(instance))
            except Exception as e:
                return HttpResponse("Validation failed: {}".format(e))

    if request.method == 'POST' and not nopostprocess:
        extra_error = None
        if allow_delete and request.POST['submit'] == 'Delete':
            if instance.pk:
                # Are there any associated objects here, by any chance?
                collector = NestedObjects(using='default')
                collector.collect([instance, ])
                to_delete = collector.nested()
                to_delete.remove(instance)
                if to_delete:
                    to_delete = [d for d in flatten_list(to_delete[0]) if d._meta.model_name not in formclass.auto_cascade_delete_to]
                if to_delete:
                    pieces = [str(to_delete[n]) for n in range(0, min(5, len(to_delete))) if not isinstance(to_delete[n], list)]
                    extra_error = "This {0} cannot be deleted. It would have resulted in the following other objects also being deleted: {1}".format(formclass.Meta.model._meta.verbose_name, ', '.join(pieces))
                else:
                    messages.info(request, "{0} {1} deleted.".format(formclass.Meta.model._meta.verbose_name.capitalize(), instance))
                    instance.delete()
                    return HttpResponseRedirect(deleted_url)
            else:
                messages.warning(request, "New {0} not deleted, object was never saved.".format(formclass.Meta.model._meta.verbose_name.capitalize()))
                return HttpResponseRedirect(cancel_url)

        form = formclass(conference, instance=instance, data=request.POST, newformdata=newformdata)
        if extra_error:
            form.add_error(None, extra_error)

        if form.is_valid():
            # If there are any file fields, they have to be independently verified
            # since the django default form handling doesn't care about them.
            errors = False
            for f in form.file_fields:
                r = form.validate_file(f, request.FILES.get(f, None))
                if r:
                    form.add_error(f, r)
                    errors = True

            if not errors:
                # We don't want to use form.save(), because it actually saves all
                # fields on the model, including those we don't care about.
                # The savem2m model, however, *does* care about the listed fields.
                # Consistency is overrated!
                with transaction.atomic():
                    if allow_new and ((not instance.pk) or form.force_insert):
                        form.pre_create_item()
                        form.save()
                    form._save_m2m()
                    for f in form.file_fields:
                        if f in request.FILES:
                            setattr(form.instance, f, request.FILES[f])
                    all_excludes = ['_validator', '_newformdata'] + form.readonly_fields
                    if form.json_form_fields:
                        for fn, ffields in form.json_form_fields.items():
                            all_excludes.extend(ffields)

                    form.instance.save(update_fields=[f for f in form.fields.keys() if f not in all_excludes and not isinstance(form[f].field, forms.ModelMultipleChoiceField)])

                    # Merge fields stored in json
                    if form.json_form_fields:
                        for fn, ffields in form.json_form_fields.items():
                            setattr(form.instance, fn, {fld: form.cleaned_data[fld] for fld in ffields})
                        form.instance.save(update_fields=form.json_form_fields.keys())

                    return HttpResponseRedirect(saved_url)
    else:
        form = formclass(conference, instance=instance, newformdata=newformdata)

    if instance.pk:
        try:
            adminurl = reverse('admin:{0}_{1}_change'.format(instance._meta.app_label, instance._meta.model_name), args=(instance.pk,))
        except NoReverseMatch:
            adminurl = None
        what = formclass.Meta.model._meta.verbose_name
    else:
        adminurl = None
        what = 'new {0}'.format(formclass.Meta.model._meta.verbose_name)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': basetemplate,
        'topadmin': topadmin,
        'form': form,
        'id': instance.pk,
        'what': what,
        'cancelurl': cancel_url,
        'breadcrumbs': breadcrumbs,
        'helplink': form.helplink,
        'allow_delete': allow_delete and instance.pk,
        'adminurl': adminurl,
        'linked': [(url, handler, handler.get_list(form.instance)) for url, handler in list(form.linked_objects.items()) if form.instance],
    })


def backend_list_editor(request, urlname, formclass, resturl, allow_new=True, allow_delete=True, conference=None, breadcrumbs=[], bypass_conference_filter=False, instancemaker=None, return_url='../', topadmin=None):
    if not conference and not bypass_conference_filter:
        conference = get_authenticated_conference(request, urlname)

    if topadmin:
        basetemplate = 'adm/admin_base.html'
    else:
        basetemplate = 'confreg/confadmin_base.html'

    if resturl:
        resturl = resturl.rstrip('/')
    if resturl == '' or resturl is None:
        # Render the list of objects
        if bypass_conference_filter:
            objects = formclass.Meta.model.objects.all()
        else:
            if hasattr(formclass.Meta, 'conference_queryset'):
                objects = formclass.Meta.conference_queryset(conference).all()
            else:
                objects = formclass.Meta.model.objects.filter(conference=conference)
        if formclass.list_order_by:
            objects = objects.order_by(*formclass.list_order_by)

        if request.method == "POST":
            if request.POST.get('operation') == 'assign':
                what = request.POST.get('what')
                related = formclass.Meta.model._meta.get_field(what).related_model
                setval = request.POST.get('assignid')
                if setval:
                    setval = int(setval)
                if what not in formclass.Meta.fields:
                    # Trying to update invalid field!
                    raise PermissionDenied()
                with transaction.atomic():
                    for obj in objects.filter(id__in=request.POST.get('idlist').split(',')):
                        if setval:
                            setattr(obj, what, related.objects.get(pk=setval))
                        else:
                            setattr(obj, what, None)
                        obj.save()
                return HttpResponseRedirect('.')
            else:
                raise Http404()

        values = [{'id': o.pk, 'vals': [getattr(o, '_display_{0}'.format(f), getattr(o, f)) for f in formclass.list_fields]} for o in objects]

        return render(request, 'confreg/admin_backend_list.html', {
            'conference': conference,
            'basetemplate': basetemplate,
            'topadmin': topadmin,
            'values': values,
            'title': formclass.Meta.model._meta.verbose_name_plural.capitalize(),
            'singular_name': formclass.Meta.model._meta.verbose_name,
            'plural_name': formclass.Meta.model._meta.verbose_name_plural,
            'headers': [formclass.get_field_verbose_name(f) for f in formclass.list_fields],
            'coltypes': formclass.coltypes,
            'filtercolumns': formclass.get_column_filters(conference),
            'defaultsort': formclass.defaultsort,
            'return_url': return_url,
            'allow_new': allow_new,
            'allow_delete': allow_delete,
            'allow_copy_previous': formclass.allow_copy_previous,
            'allow_email': formclass.allow_email,
            'assignable_columns': formclass.get_assignable_columns(conference),
            'breadcrumbs': breadcrumbs,
            'helplink': formclass.helplink,
        })

    if allow_new and resturl == 'new':
        # This one is more interesting...
        return backend_process_form(request,
                                    urlname,
                                    formclass,
                                    None,
                                    allow_new=True,
                                    allow_delete=allow_delete,
                                    breadcrumbs=breadcrumbs + [('../', formclass.Meta.model._meta.verbose_name_plural.capitalize()), ],
                                    conference=conference,
                                    bypass_conference_filter=bypass_conference_filter,
                                    instancemaker=instancemaker,
                                    topadmin=topadmin,
        )

    restpieces = resturl.split('/')
    if formclass.allow_copy_previous and restpieces[0] == 'copy':
        return backend_handle_copy_previous(request, formclass, restpieces, conference)

    # Is it an id?
    try:
        id = int(restpieces[0])
    except ValueError:
        # No id. So we don't know. Fail.
        raise Http404()

    if len(restpieces) > 2 and restpieces[1] in formclass.linked_objects:
        # We are editing a sub-object!

        handler = formclass.linked_objects[restpieces[1]]
        if conference:
            if hasattr(formclass.Meta, 'conference_queryset'):
                masterobj = formclass.Meta.conference_queryset(conference).get(pk=id)
            else:
                masterobj = formclass.Meta.model.objects.get(pk=id, conference=conference)
        else:
            masterobj = formclass.Meta.model.objects.get(pk=id)

        if restpieces[2] == 'new':
            subid = None
            subobj = None
        else:
            try:
                subid = int(restpieces[2])
                subobj = handler.get_object(masterobj, subid)
                if not subobj:
                    raise Http404()
            except ValueError:
                # No proper subid. So fail.
                raise Http404()

        return backend_process_form(request,
                                    urlname,
                                    handler.get_form(subobj, request.POST),
                                    subid,
                                    breadcrumbs=breadcrumbs + [
                                        ('../../../', formclass.Meta.model._meta.verbose_name_plural.capitalize()),
                                        ('../../', masterobj),
                                    ],
                                    cancel_url='../../',
                                    saved_url='../../',
                                    conference=conference,
                                    bypass_conference_filter=True,
                                    instancemaker=handler.get_instancemaker(masterobj),
                                    topadmin=topadmin,
        )

    if len(restpieces) > 1:
        raise Http404()

    return backend_process_form(request,
                                urlname,
                                formclass,
                                id,
                                allow_delete=allow_delete,
                                breadcrumbs=breadcrumbs + [('../', formclass.Meta.model._meta.verbose_name_plural.capitalize()), ],
                                conference=conference,
                                bypass_conference_filter=bypass_conference_filter,
                                topadmin=topadmin,
    )


def backend_handle_copy_previous(request, formclass, restpieces, conference):
    if len(restpieces) == 1:
        # No conference selected yet, so start by doing that
        if request.method == 'POST':
            form = BackendCopySelectConferenceForm(request, conference, formclass.Meta.model, data=request.POST)
            if form.is_valid():
                return HttpResponseRedirect("{0}/".format(form.cleaned_data.get('conference').pk))
        else:
            form = BackendCopySelectConferenceForm(request, conference, formclass.Meta.model)
        return render(request, 'confreg/admin_backend_copy_select_conf.html', {
            'conference': conference,
            'form': form,
            'what': formclass.Meta.model._meta.verbose_name,
            'savebutton': 'Copy',
            'cancelurl': '../',
            'breadcrumbs': [('../', formclass.Meta.model._meta.verbose_name_plural.capitalize()), ],
            'helplink': formclass.helplink,
        })
    elif len(restpieces) == 2:
        idlist = None
        confirmed_transform_value = None
        confirmed_transform_example = None
        sourceconfid = int(restpieces[1])
        sourceconf = get_authenticated_conference(request, confid=sourceconfid)

        if request.method == "POST":
            idlist = sorted([int(k[2:]) for k, v in list(request.POST.items()) if k.startswith('c_') and v == '1'])
            if formclass.copy_transform_form:
                # First validate the transform form
                transform_form = formclass.copy_transform_form(conference, sourceconf, data=request.POST)
                if transform_form.is_valid():
                    # Transform input is valid, but is it correct?
                    if request.POST.get('confirmed_transform', '') == transform_form.confirm_value():
                        with transaction.atomic():
                            errors = list(formclass.copy_from_conference(conference, sourceconf, idlist, transform_form))
                            if errors:
                                for e in errors:
                                    messages.error(request, e)
                                    transaction.set_rollback(True)
                                    # Fall-through and re-render the form
                            else:
                                return HttpResponseRedirect("../../")
                    else:
                        # Transform input is valid, but it has not been confirmed.
                        confirmed_transform_example = formclass.get_transform_example(conference, sourceconf, idlist, transform_form)
                        if confirmed_transform_example:
                            confirmed_transform_value = transform_form.confirm_value()
                        # Fall-through to re-render the form
            else:
                with transaction.atomic():
                    errors = list(formclass.copy_from_conference(conference, sourceconf, idlist))
                    if errors:
                        for e in errors:
                            messages.error(request, e)
                        transaction.set_rollback(True)
                        transform_form = None
                        # Fall through and re-render our forms
                    else:
                        return HttpResponseRedirect("../../")

        else:
            if formclass.copy_transform_form:
                transform_form = formclass.copy_transform_form(conference, sourceconf)
            else:
                transform_form = None

        objects = formclass.Meta.model.objects.filter(conference=sourceconf)
        values = [{'id': o.pk, 'vals': [getattr(o, '_display_{0}'.format(f), getattr(o, f)) for f in formclass.list_fields]} for o in objects]
        return render(request, 'confreg/admin_backend_list.html', {
            'conference': conference,
            'basetemplate': 'confreg/confadmin_base.html',
            'values': values,
            'title': formclass.Meta.model._meta.verbose_name_plural.capitalize(),
            'singular_name': formclass.Meta.model._meta.verbose_name,
            'plural_name': formclass.Meta.model._meta.verbose_name_plural,
            'headers': [formclass.get_field_verbose_name(f) for f in formclass.list_fields],
            'coltypes': formclass.coltypes,
            'filtercolumns': formclass.get_column_filters(conference),
            'defaultsort': formclass.defaultsort,
            'return_url': '../',
            'allow_new': False,
            'allow_delete': False,
            'allow_copy_previous': False,
            'is_copy_previous': True,
            'transform_form': transform_form,
            'idlist': idlist,
            'confirmed_transform_value': confirmed_transform_value,
            'transform_example': confirmed_transform_example,
            'noeditlinks': True,
            'breadcrumbs': [
                ('../../', formclass.Meta.model._meta.verbose_name_plural.capitalize()),
                ('../', 'Copy {0}'.format(formclass.Meta.model._meta.verbose_name_plural.capitalize())),
            ],
            'helplink': formclass.helplink,
        })
