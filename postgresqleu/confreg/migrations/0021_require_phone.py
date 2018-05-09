# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0020_unique_regdays'),
    ]

    operations = [
        migrations.AddField(
            model_name='registrationtype',
            name='require_phone',
            field=models.BooleanField(default=False, help_text=b'Require phone number to be entered'),
        ),
    ]
