# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ErrorLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField()),
                ('message', models.TextField()),
                ('sent', models.BooleanField()),
            ],
        ),
        migrations.CreateModel(
            name='SourceAccount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('accountname', models.CharField(max_length=16)),
                ('lastsync', models.DateTimeField(default=datetime.datetime(2009, 1, 1, 0, 0))),
            ],
        ),
        migrations.CreateModel(
            name='TransactionInfo',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('paypaltransid', models.CharField(unique=True, max_length=20)),
                ('timestamp', models.DateTimeField()),
                ('sender', models.CharField(max_length=200)),
                ('sendername', models.CharField(max_length=200)),
                ('amount', models.DecimalField(max_digits=10, decimal_places=2)),
                ('fee', models.DecimalField(null=True, max_digits=10, decimal_places=2, blank=True)),
                ('transtext', models.CharField(max_length=1000)),
                ('matched', models.BooleanField()),
                ('matchinfo', models.CharField(max_length=1000, null=True, blank=True)),
                ('sourceaccount', models.ForeignKey(to='paypal.SourceAccount')),
            ],
        ),
    ]
