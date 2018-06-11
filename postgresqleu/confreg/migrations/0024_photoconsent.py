# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0023_accesstokens'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='askphotoconsent',
            field=models.BooleanField(default=True, help_text=b'Include field for getting photo consent', verbose_name=b'Field: photo consent'),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='photoconsent',
            field=models.NullBooleanField(verbose_name=b'Consent to having your photo taken at the event by the organisers'),
        ),
    ]
