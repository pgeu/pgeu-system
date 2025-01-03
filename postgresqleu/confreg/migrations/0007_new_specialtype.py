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
            field=models.CharField(blank=True, choices=[('man', 'Manually confirmed'), ('spk', 'Confirmed speaker'), ('spkr', 'Confirmed or reserve speaker'), ('staff', 'Confirmed staff'), ('vch', 'Requires specific voucher')], max_length=5, null=True, verbose_name='Special type'),
        ),
    ]
