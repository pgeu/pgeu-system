# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import postgresqleu.confwiki.models


class Migration(migrations.Migration):

    dependencies = [
        ('confwiki', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='signup',
            name='optionvalues',
            field=models.CharField(blank=True, help_text='Optional comma separated list of how much each choice counts towards the max value', max_length=1000, validators=[postgresqleu.confwiki.models.validate_optionvalues]),
        ),
    ]
