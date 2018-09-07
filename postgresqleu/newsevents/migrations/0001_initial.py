# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('countries', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=128)),
                ('startdate', models.DateField()),
                ('enddate', models.DateField()),
                ('city', models.CharField(max_length=128)),
                ('state', models.CharField(max_length=8, blank=True)),
                ('summary', models.TextField()),
                ('country', models.ForeignKey(to='countries.Country', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ['startdate', 'title'],
            },
        ),
        migrations.CreateModel(
            name='News',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=128)),
                ('datetime', models.DateTimeField()),
                ('summary', models.TextField()),
            ],
            options={
                'ordering': ['-datetime', 'title'],
                'verbose_name_plural': 'News',
            },
        ),
    ]
