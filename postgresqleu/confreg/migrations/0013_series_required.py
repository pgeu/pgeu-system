# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0012_mandatory_tokens'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conference',
            name='series',
            field=models.ForeignKey(to='confreg.ConferenceSeries', on_delete=models.CASCADE),
        ),
    ]
