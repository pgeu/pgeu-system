# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0004_anothervat'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsor',
            name='vatstatus',
            field=models.IntegerField(default=-1, choices=[(0, b'Company is from inside EU and has VAT number'), (1, b'Company is from inside EU, but does not have VAT number'), (2, b'Company is from outside EU')]),
            preserve_default=False,
        ),
    ]
