# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0014_check_constraint_token'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='conference',
            name='badgemodule',
        ),
        migrations.RemoveField(
            model_name='conference',
            name='basetemplate',
        ),
        migrations.RemoveField(
            model_name='conference',
            name='templatemediabase',
        ),
        migrations.RemoveField(
            model_name='conference',
            name='templatemodule',
        ),
        migrations.RemoveField(
            model_name='conference',
            name='templateoverridedir',
        ),
    ]
