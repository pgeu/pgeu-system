# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsor',
            name='displayname',
            field=models.CharField(max_length=100, null=True),
            preserve_default=False,
        ),
		migrations.RunSQL("UPDATE confsponsor_sponsor SET displayname=name"),
		migrations.AlterField(
			model_name='sponsor',
			name='displayname',
			field=models.CharField(max_length=100),
		),
        migrations.AddField(
            model_name='sponsor',
            name='url',
            field=models.URLField(blank=True),
        ),
    ]
