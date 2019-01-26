from django.db import connection

from datetime import datetime, timedelta


def notify_job_change():
    with connection.cursor() as curs:
        curs.execute("NOTIFY pgeu_scheduled_job")


def _get_next_time(times):
    # Next time will be the first one that's after current time
    current = datetime.now().time()
    stimes = sorted(times)
    for t in stimes:
        if t > current:
            return datetime.now().replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
            break
    else:
        return datetime.now().replace(hour=stimes[0].hour,
                                      minute=stimes[0].minute,
                                      second=stimes[0].second,
                                      microsecond=0) + timedelta(hours=24)


# Calculate the next time for this job
def reschedule_job(job, save=True, notify=False):
    if (notify and not save):
        raise Exception("It makes no sense to notify if not saving!")

    if not job.enabled:
        if job.nextrun:
            job.nextrun = None
            if save:
                job.save()
        return

    newtime = None
    # First check for overrides
    if job.override_interval:
        newtime = job.last_run_or_skip(datetime.now()) + job.override_interval
    elif job.override_times:
        newtime = _get_next_time(job.override_times)
    elif job.scheduled_interval:
        newtime = job.last_run_or_skip(datetime.now()) + job.scheduled_interval
    elif job.scheduled_times:
        newtime = _get_next_time(job.scheduled_times)

    job.nextrun = newtime
    if save:
        job.save()
        if notify:
            notify_job_change()
