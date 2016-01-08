# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('membership', '0001_initial'),
        ('elections', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vote',
            name='voter',
            field=models.ForeignKey(to='membership.Member'),
        ),
        migrations.AddField(
            model_name='candidate',
            name='election',
            field=models.ForeignKey(to='elections.Election'),
        ),
    ]
