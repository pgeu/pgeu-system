# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0002_auto_20160108_1924'),
    ]

    operations = [
        migrations.AlterField(
            model_name='discountcode',
            name='requiresregtype',
            field=models.ManyToManyField(help_text=b'Require a specific registration type to be valid', to='confreg.RegistrationType', blank=True),
        ),
    ]
