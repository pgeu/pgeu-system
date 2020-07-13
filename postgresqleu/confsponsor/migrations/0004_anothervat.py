# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0003_vat'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='sponsor',
            name='invatarea',
        ),
    ]
