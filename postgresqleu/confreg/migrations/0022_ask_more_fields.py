# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0021_require_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='asknick',
            field=models.BooleanField(default=True, help_text=b'Include field for nick', verbose_name=b'Field: nick'),
        ),
        migrations.AddField(
            model_name='conference',
            name='asktwitter',
            field=models.BooleanField(default=True, help_text=b'Include field for twitter name', verbose_name=b'Field: twitter name'),
        ),
        migrations.AlterField(
            model_name='conference',
            name='asknick',
            field=models.BooleanField(default=False, help_text=b'Include field for nick', verbose_name=b'Field: nick'),
        ),
        migrations.AlterField(
            model_name='conference',
            name='asktwitter',
            field=models.BooleanField(default=False, help_text=b'Include field for twitter name', verbose_name=b'Field: twitter name'),
        ),
    ]
