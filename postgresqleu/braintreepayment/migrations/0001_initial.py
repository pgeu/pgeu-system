# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BraintreeLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('transid', models.CharField(max_length=100)),
                ('message', models.TextField()),
                ('error', models.BooleanField(default=False)),
                ('sent', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='BraintreeTransaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('transid', models.CharField(unique=True, max_length=100)),
                ('authorizedat', models.DateTimeField()),
                ('settledat', models.DateTimeField(null=True, blank=True)),
                ('disbursedat', models.DateTimeField(null=True, blank=True)),
                ('amount', models.IntegerField()),
                ('disbursedamount', models.DecimalField(null=True, max_digits=20, decimal_places=2, blank=True)),
                ('method', models.CharField(max_length=100, null=True, blank=True)),
                ('accounting_object', models.CharField(max_length=30, null=True, blank=True)),
            ],
        ),
    ]
