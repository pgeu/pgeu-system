# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('membership', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='country_exception',
            field=models.BooleanField(default=False, help_text=b'Enable to allow member to bypass country validation'),
        ),
    ]
