# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0009_confslides'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='volunteerslot',
            options={'ordering': ['timerange']},
        ),
        migrations.AlterField(
            model_name='conferencesessionslides',
            name='url',
            field=models.URLField(max_length=1000, blank=True, verbose_name='URL'),
        ),
    ]
