from django import forms

from postgresqleu.util.backendforms import BackendForm
from .models import ScheduledJob


class ScheduledJobForm(BackendForm):
    class Meta:
        model = ScheduledJob
        fields = ('app', 'command', 'description', 'enabled', 'notifyonsuccess',
                  'scheduled_times', 'override_times', 'scheduled_interval', 'override_interval',)

    readonly_fields = ['app', 'command', 'description', 'scheduled_times', 'scheduled_interval', ]

    fieldsets = [
        {
            'id': 'general',
            'legend': 'General settings',
            'fields': ['app', 'command', 'description', 'enabled', 'notifyonsuccess', ],
        },
        {
            'id': 'schedule',
            'legend': 'Schedule',
            'fields': ['scheduled_times', 'override_times', 'scheduled_interval', 'override_interval', ],
        }
    ]

    def clean_override_times(self):
        val = self.cleaned_data.get('override_times')
        if val == self.instance.scheduled_times:
            val = None
        return val

    def clean_override_interval(self):
        val = self.cleaned_data.get('override_interval')
        if val == self.instance.scheduled_interval:
            val = None
        return val
