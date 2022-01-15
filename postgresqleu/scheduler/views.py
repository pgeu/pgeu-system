from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, Http404
from django.contrib import messages
from django.db import connection
from django.db.models import F
from django.apps import apps
from django.utils import timezone

from datetime import datetime, timedelta

from postgresqleu.util.pagination import simple_pagination
from postgresqleu.util.request import get_int_or_error

from .models import ScheduledJob, JobHistory, get_config
from .forms import ScheduledJobForm
from .util import reschedule_job, notify_job_change


def index(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    config = get_config()

    if request.method == 'POST':
        if request.POST.get('submit') == 'Hold all jobs':
            config.hold_all_jobs = True
            config.save()
            notify_job_change()
            return HttpResponseRedirect('.')
        elif request.POST.get('submit') == 'Re-enable job execution':
            what = get_int_or_error(request.POST, 'pending')
            if what == 0:
                messages.error(request, "Must decide what to do with pending jobs")
                return HttpResponseRedirect(".")
            elif what not in (1, 2):
                messages.error(request, "Invalid choice for pending jobs")
                return HttpResponseRedirect(".")

            if what == 2:
                # Re-schedule all pending jobs
                for job in ScheduledJob.objects.filter(enabled=True, nextrun__lte=timezone.now()):
                    reschedule_job(job, save=True)
            config.hold_all_jobs = False
            config.save()
            notify_job_change()
            messages.info(request, "Job execution re-enabled")
            return HttpResponseRedirect(".")

        raise Http404("Unknown button")

    jobs = ScheduledJob.objects.all().order_by(F('nextrun').asc(nulls_last=True))
    try:
        lastjob = ScheduledJob.objects.only('lastrun').filter(lastrun__isnull=False).order_by('-lastrun')[0]
        lastjobtime = lastjob.lastrun
        lastjob_recent = (timezone.now() - lastjobtime) < timedelta(hours=6)
    except IndexError:
        # No job has run yet, can happen on brand new installation
        lastjobtime = None
        lastjob_recent = False

    history = JobHistory.objects.only('time', 'job__description', 'success', 'runtime').select_related('job').order_by('-time')[:20]

    with connection.cursor() as curs:
        curs.execute("SELECT count(1) FROM pg_stat_activity WHERE application_name='pgeu scheduled job runner' AND datname=current_database()")
        n, = curs.fetchone()
        runner_active = (n > 0)

    return render(request, 'scheduler/index.html', {
        'jobs': jobs,
        'lastjob': lastjobtime,
        'lastjob_recent': lastjob_recent,
        'runner_active': runner_active,
        'holdall': config.hold_all_jobs,
        'history': history,
        'apps': {a.name: a.verbose_name for a in apps.get_app_configs()},
        'helplink': 'jobs',
    })


def job(request, jobid):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    job = get_object_or_404(ScheduledJob, id=jobid)

    if request.method == 'POST':
        if request.POST.get('schedule-now', '') == '1':
            job.nextrun = timezone.now()
            job.save()
            notify_job_change()
            messages.info(request, "Scheduled immediate run of '{0}'".format(job.description))
            return HttpResponseRedirect('../')
        elif request.POST.get('reset-failure', '') == '1':
            job.lastrun = None
            job.lastrunsuccess = False
            job.save()
            messages.info(request, "Reset last run failure state of '{0}'".format(job.description))
            return HttpResponseRedirect('../')

        form = ScheduledJobForm(request, conference=None, instance=job, data=request.POST)
        if form.is_valid():
            form.save()
            reschedule_job(job, notify=True)
            return HttpResponseRedirect("../")
    else:
        form = ScheduledJobForm(request, conference=None, instance=job)

    history_objects = JobHistory.objects.filter(job=job).order_by('-time')
    (history, paginator, page_range) = simple_pagination(request, history_objects, 15)

    return render(request, 'scheduler/job.html', {
        'job': job,
        'history': history,
        'form': form,
        'page_range': page_range,
        'breadcrumbs': [('/admin/jobs/', 'Scheduled jobs'), ],
        'helplink': 'jobs',
    })


def history(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    history_objects = JobHistory.objects.only('time', 'job__description', 'success', 'runtime').select_related('job').order_by('-time')
    (history, paginator, page_range) = simple_pagination(request, history_objects, 50)

    return render(request, 'scheduler/history.html', {
        'history': history,
        'page_range': page_range,
        'breadcrumbs': [('/admin/jobs/', 'Scheduled jobs'), ],
        'helplink': 'jobs',
    })
