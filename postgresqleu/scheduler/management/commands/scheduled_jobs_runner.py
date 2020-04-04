#
# Run all scheduled jobs
#
# Intended to run continously and will never exit. Will, however,
# crash on database loss for example, so should be run from an init
# handler that automaticaly restarts (after some delay)
#

from django.core.management.base import BaseCommand, CommandError
from django.core.management import load_command_class
from django.db import connection
from django.utils import autoreload, timezone
from django.conf import settings

from datetime import timedelta
import time
import io
import sys
import os
import subprocess
import threading
import select

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.scheduler.util import reschedule_job
from postgresqleu.scheduler.models import ScheduledJob, JobHistory, get_config


class Command(BaseCommand):
    help = 'Run all scheduled jobs'

    def handle(self, *args, **options):
        # Automatically exit if our own code changes.
        # This is not based on a published API, so quite likely will fail
        # and need to be updated in a future version of django

        # Start our work in a background thread
        bthread = threading.Thread(target=self.inner_handle)
        bthread.setDaemon(True)
        bthread.start()

        reloader = autoreload.get_reloader()
        while not reloader.should_stop:
            reloader.run(bthread)

        self.stderr.write("Underlying code changed, exiting for a restart")
        sys.exit(0)

    def inner_handle(self):
        with connection.cursor() as curs:
            curs.execute("LISTEN pgeu_scheduled_job")
            curs.execute("SET application_name = 'pgeu scheduled job runner'")

        while True:
            if get_config().hold_all_jobs:
                self.stderr.write("All jobs are being held, sleeping for 10 minutes and then reconsidering")
                self.eat_notifications()
                select.select([connection.connection], [], [], 600)
                continue

            self.run_pending_jobs()

            # Find when the next job runs, and sleep until then
            nextjob = ScheduledJob.objects.only('nextrun').filter(enabled=True).order_by('nextrun')[0]
            # Find seconds until next job. Add one second to make sure we don't end up in a tight loop due
            # to time roundoff.
            secondsuntil = int((nextjob.nextrun - timezone.now()).total_seconds() + 1)
            if secondsuntil < 2:
                self.stderr.write("Timeout to next job already expired, sleeping 1 second and then re-running queue.")
                time.sleep(1)
            else:
                self.stderr.write("Sleeping {0} seconds until {1}".format(secondsuntil, nextjob.nextrun))
                # This sleep is done while listening for PostgreSQL NOTIFY in case a job is
                # being rescheduled from the web interface (or elsewhere in the system).

                # First eat any existing notifications
                self.eat_notifications()

                # Then wait for either the number of seconds specified or until something
                # shows up on our connection. That is normally the result of a NOTIFY, so
                # we don't bother checking what it is, and just continue in the next loop.
                select.select([connection.connection], [], [], secondsuntil)

    def eat_notifications(self):
        connection.connection.poll()
        while connection.connection.notifies:
            connection.connection.notifies.pop()

    def run_pending_jobs(self):
        while True:
            jobs = ScheduledJob.objects.filter(nextrun__lte=timezone.now(), enabled=True)
            if not jobs:
                # Nothing left to do!
                return

            for job in jobs:
                # Start by finding the command class itself
                try:
                    cmd = load_command_class(job.app, job.command)
                    if hasattr(cmd.ScheduledJob, 'should_run'):
                        # If method should_run exists, call it and figure out if the job should
                        # run. If we get an excpetion in this check, we make sure to run the job,
                        # to be on the safe side.
                        try:
                            if not cmd.ScheduledJob.should_run():
                                self.stderr.write("Skipping job {}".format(job.description))
                                job.lastskip = timezone.now()
                                reschedule_job(job, save=True)
                                continue
                        except Exception as e:
                            sys.stderr.write("Exception when trying to figure out if '{0}' should run:\n{1}\n\nJob will be run.\n".format(job.description, e))

                    self.stderr.write("Running job {}".format(job.description))
                    # Now figure out what type of job it is, and run it
                    job.lastrunsuccess = self.run_job(job, cmd)
                    job.lastrun = timezone.now()
                    job.lastskip = None
                    reschedule_job(job, save=True)

                    # A job can define one or more other jobs to schedule immediately
                    # after this job has completed.
                    if hasattr(cmd.ScheduledJob, 'trigger_next_jobs'):
                        if isinstance(cmd.ScheduledJob.trigger_next_jobs, str):
                            nextjobs = [cmd.ScheduledJob.trigger_next_jobs, ]
                        elif isinstance(cmd.ScheduledJob.trigger_next_jobs, list) or isinstance(cmd.ScheduledJob.trigger_next_jobs, tuple):
                            nextjobs = cmd.ScheduledJob.trigger_next_jobs
                        else:
                            raise Exception("trigger_next_jobs must be string or iterable!")

                        for j in nextjobs:
                            try:
                                pieces = j.split('.')
                                sj = ScheduledJob.objects.get(app='.'.join(pieces[:-1]),
                                                              command=pieces[-1])
                                sj.nextrun = timezone.now()
                                sj.save()
                            except ScheduledJob.DoesNotExist:
                                self.stderr.write("Could not find job {} to run after {}".format(j, job.description))
                                # But it's not critical, so we don't bother notifying

                except Exception as e:
                    # Hard exception at the top level will cause us to disbale
                    # the job.
                    job.lastrun = timezone.now()
                    job.lastrunsuccess = False
                    job.enabled = False
                    job.nextrun = None
                    job.save()
                    JobHistory(job=job,
                               time=timezone.now(),
                               success=False,
                               runtime=timedelta(),
                               output="Internal exception:\n{0}\n\nJob has been disabled".format(e),
                    ).save()
                    self.send_notification_email("Exception running scheduled job",
                                                 "Job has been disbaled.\nException:\n{0}\n".format(e))

    def run_job(self, job, cmd):
        starttime = time.time()
        if getattr(cmd.ScheduledJob, 'internal', False):
            (output, success) = self.run_internal_job(job, cmd)
        else:
            (output, success) = self.run_external_job(job, cmd)

        # Create a job history record. The caller will update the main job entry,
        # but we want to store the output.
        JobHistory(job=job,
                   time=timezone.now(),
                   success=success,
                   runtime=timedelta(seconds=time.time() - starttime),
                   output=output.getvalue(),
        ).save()

        if success and job.notifyonsuccess and output.tell():
            # Only send successful notification email if there was some output (this
            # basically mimics what cron does, but we only do it selectively)
            self.send_notification_email("scheduled job '{0}' completed".format(job.description),
                                         output.getvalue())
        elif not success:
            self.send_notification_email("Scheduled job '{0}' failed".format(job.description),
                                         output.getvalue())

        return success

    def run_internal_job(self, job, cmd):
        # Internal jobs are run in our own process and as such don't
        # have timeouts or anything like that.
        output = io.StringIO()
        success = False

        try:
            cmd.execute(no_color=True,
                        stdout=output,
                        stderr=output)
            success = True
        except Exception as e:
            output.write("**** EXCEPTION ****\n")
            output.write(str(e))
            output.write("\n")

        return (output, success)

    def run_external_job(self, job, cmd):
        # External jobs are run in an external process with a timeout, as set in the
        # job. If it's not set, it will be set to 2 minutes.
        timeout = getattr(cmd.ScheduledJob, 'timeout', 2)
        timeout_seconds = timeout * 60

        fullout = io.StringIO()
        success = False

        # Figure out our python
        try:
            output = subprocess.check_output(
                [sys.executable, os.path.abspath("{0}/../manage.py".format(settings.PROJECT_ROOT)), job.command],
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
            )
            if output:
                fullout.write(output.decode('utf8', errors='ignore'))
            success = True
        except subprocess.TimeoutExpired as e:
            fullout.write("Timeout of {0} seconds expired.".format(timeout_seconds))
        except subprocess.CalledProcessError as cpe:
            fullout.write("Exit code {0}\n\n".format(cpe.returncode))
            fullout.write(cpe.output.decode('utf8', errors='ignore'))
            fullout.write("\n")

        return (fullout, success)

    def send_notification_email(self, subject, contents):
        send_simple_mail(
            settings.SCHEDULED_JOBS_EMAIL_SENDER,
            settings.SCHEDULED_JOBS_EMAIL,
            subject,
            contents,
        )
