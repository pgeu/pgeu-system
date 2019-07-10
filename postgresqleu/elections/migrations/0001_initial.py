# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from postgresqleu.util.fields import LowercaseEmailField


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Candidate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('email', LowercaseEmailField(max_length=200)),
                ('presentation', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='Election',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('startdate', models.DateField()),
                ('enddate', models.DateField()),
                ('slots', models.IntegerField(default=1)),
                ('isopen', models.BooleanField(default=False, verbose_name="Voting open")),
                ('resultspublic', models.BooleanField(default=False, verbose_name="Results public")),
            ],
            options={
                'ordering': ('-startdate',),
            },
        ),
        migrations.CreateModel(
            name='Vote',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('score', models.IntegerField()),
                ('candidate', models.ForeignKey(to='elections.Candidate', on_delete=models.CASCADE)),
                ('election', models.ForeignKey(to='elections.Election', on_delete=models.CASCADE)),
            ],
        ),
    ]
