# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('membership', '0002_member_country_exception'),
    ]

    operations = [
        migrations.AddField(
            model_name='membermeetingkey',
            name='proxyaccesskey',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='membermeetingkey',
            name='proxyname',
            field=models.CharField(max_length=200, null=True),
        ),
    ]
