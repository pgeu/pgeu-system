from django.core.validators import ValidationError
from django.db import models
from django.contrib.postgres.fields import ArrayField


class SchedulerConfig(models.Model):
    hold_all_jobs = models.BooleanField(default=False)


def get_config():
    return SchedulerConfig.objects.get(pk=1)


class ScheduledJob(models.Model):
    app = models.CharField(max_length=200, null=False, blank=False)
    command = models.CharField(max_length=100, null=False, blank=False, unique=True)
    description = models.CharField(max_length=200, null=False, blank=False)
    enabled = models.BooleanField(default=True)
    notifyonsuccess = models.BooleanField(default=False, verbose_name="Notify on success",
                                          help_text="Send notification email even if job is successful")

    nextrun = models.DateTimeField(null=True, blank=True)

    lastrun = models.DateTimeField(null=True, blank=True)
    lastrunsuccess = models.BooleanField(default=False)
    lastskip = models.DateTimeField(null=True, blank=True)

    scheduled_times = ArrayField(models.TimeField(), null=True, blank=True)
    scheduled_interval = models.DurationField(null=True, blank=True)

    override_times = ArrayField(models.TimeField(), null=True, blank=True,
                                help_text="Specify a comma separated list of times (hour:minute:second) to override the default schedule")
    override_interval = models.DurationField(null=True, blank=True,
                                             help_text="Specify an interval (hours:minutes:seconds) to override the default schedule")

    class Meta:
        unique_together = (
            ('app', 'command'),
        )

    def __str__(self):
        return self.classname

    def clean(self):
        if self.scheduled_times and self.scheduled_interval:
            raise ValidationError("Cannot specify both scheduled times and scheduled interval!")
        if self.override_times and self.override_interval:
            s = "Cannot specify both override times and override interval!"
            raise ValidationError({
                'override_times': s,
                'override_interval': s,
            })

    def last_run_or_skip(self, fallback):
        if self.lastrun and self.lastskip:
            return max(self.lastrun, self.lastskip)
        elif self.lastrun:
            return self.lastrun
        elif self.lastskip:
            return self.lastskip
        return fallback


class JobHistory(models.Model):
    job = models.ForeignKey(ScheduledJob, null=False, blank=False)
    time = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    success = models.BooleanField(null=False)
    runtime = models.DurationField(null=False)
    output = models.TextField(null=False, blank=True)

    @property
    def first_output(self):
        if self.output:
            ll = self.output.splitlines()
            if len(ll) > 1:
                return "{0} ....".format(ll[0])
            return ll[0]
        return ''
