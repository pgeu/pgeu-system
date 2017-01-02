# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0002_add_sponsor_displayfields'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsor',
            name='invatarea',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='sponsor',
            name='vatnumber',
            field=models.CharField(max_length=100, blank=True),
        ),
    ]
