# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0005_vat'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='jinjadir',
            field=models.CharField(default=None, max_length=200, null=True, help_text='Full path to new style jinja repository root', blank=True, verbose_name='Jinja directory'),
        ),
    ]
