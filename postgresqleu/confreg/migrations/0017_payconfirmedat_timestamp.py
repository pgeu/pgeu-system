# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0016_separate_registrator'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conferenceregistration',
            name='payconfirmedat',
            field=models.DateTimeField(null=True, verbose_name='Payment confirmed at', blank=True),
        ),
    ]
