# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0003_typofix'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='timediff',
            field=models.IntegerField(default=0),
        ),
    ]
