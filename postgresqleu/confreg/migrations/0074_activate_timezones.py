# Generated by Django 2.2.11 on 2020-04-10 16:54

from django.db import migrations, connection
from django.db.models import Q
from django.conf import settings


def convert_timezones(apps, schema_editor):
    Conf = apps.get_model('confreg', 'conference')

    curs = connection.cursor()
    for c in Conf.objects.filter(~Q(tzname=settings.TIME_ZONE)):
        curs.execute("SET TIME ZONE %(tzn)s", {'tzn': c.tzname})
        curs.execute("UPDATE confreg_conferencesession SET starttime = starttime AT TIME ZONE %(tzn)s, endtime = endtime AT TIME ZONE %(tzn)s WHERE conference_id=%(confid)s", {
            'tzn': settings.TIME_ZONE,
            'confid': c.id,
        })
        curs.execute("UPDATE confreg_conferencesessionscheduleslot SET starttime = starttime AT TIME ZONE %(tzn)s, endtime = endtime AT TIME ZONE %(tzn)s WHERE conference_id=%(confid)s", {
            'tzn': settings.TIME_ZONE,
            'confid': c.id,
        })
        curs.execute("UPDATE confreg_volunteerslot SET timerange=tstzrange(lower(timerange) AT TIME ZONE %(tzn)s, upper(timerange) AT TIME ZONE %(tzn)s) WHERE conference_id=%(confid)s", {
            'tzn': settings.TIME_ZONE,
            'confid': c.id,
        })
    curs.execute("SET TIME ZONE UTC")


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0073_conference_tzname'),
    ]

    operations = [
        migrations.RunPython(convert_timezones),
        migrations.RemoveField(
            model_name='conference',
            name='timediff',
        ),
    ]
