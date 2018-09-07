# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('confreg', '0015_remove_non_jinja_conferences'),
    ]

    operations = [
        migrations.AddField(
            model_name='conferenceregistration',
            name='registrator',
            field=models.ForeignKey(related_name='registrator', blank=True, null=True, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='conferenceregistration',
            name='attendee',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE),
        ),
		migrations.RunSQL("UPDATE confreg_conferenceregistration SET registrator_id=attendee_id"),
		migrations.AlterField(
            model_name='conferenceregistration',
            name='registrator',
            field=models.ForeignKey(related_name='registrator', to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
		),
    ]
