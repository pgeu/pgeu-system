# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('countries', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EuropeCountry',
            fields=[
                ('iso', models.OneToOneField(primary_key=True, serialize=False, to='countries.Country', on_delete=models.CASCADE)),
            ],
        ),
    ]
