# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Country',
            fields=[
                ('iso', models.CharField(max_length=2, serialize=False, verbose_name='ISO alpha-2', primary_key=True)),
                ('name', models.CharField(max_length=128, verbose_name='Official name (CAPS)')),
                ('printable_name', models.CharField(max_length=128, verbose_name='Country name')),
                ('iso3', models.CharField(max_length=3, null=True, verbose_name='ISO alpha-3')),
                ('numcode', models.PositiveSmallIntegerField(null=True, verbose_name='ISO numeric')),
            ],
            options={
                'ordering': ('name',),
                'db_table': 'country',
                'verbose_name': 'Country',
                'verbose_name_plural': 'Countries',
            },
        ),
        migrations.CreateModel(
            name='UsState',
            fields=[
                ('id', models.AutoField(serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=50, verbose_name='State name')),
                ('abbrev', models.CharField(max_length=2, verbose_name='Abbreviation')),
            ],
            options={
                'ordering': ('name',),
                'db_table': 'usstate',
                'verbose_name': 'US State',
                'verbose_name_plural': 'US States',
            },
        ),
    ]
