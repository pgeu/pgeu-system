# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0024_photoconsent'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='allowedit',
            field=models.BooleanField(default=True, verbose_name=b'Allow editing registrations'),
        ),
    ]
