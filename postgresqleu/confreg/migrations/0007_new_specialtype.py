# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0006_jinjadir'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registrationtype',
            name='specialtype',
            field=models.CharField(blank=True, max_length=5, null=True, choices=[(b'man', b'Manually confirmed'), (b'spk', b'Confirmed speaker'), (b'spkr', b'Confirmed or reserve speaker'), (b'staff', b'Confirmed staff')], verbose_name="Special type"),
        ),
    ]
