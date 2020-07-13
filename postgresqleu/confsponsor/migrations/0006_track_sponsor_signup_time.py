# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0005_vatstatus'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsor',
            name='signupat',
            field=models.DateTimeField(null=True),
        ),
        migrations.RunSQL("UPDATE confsponsor_sponsor SET signupat=COALESCE(confirmedat, CURRENT_TIMESTAMP)"),
        migrations.AlterField(
            model_name='sponsor',
            name='signupat',
            field=models.DateTimeField(),
        ),
    ]
