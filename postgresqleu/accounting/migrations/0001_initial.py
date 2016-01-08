# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import postgresqleu.accounting.models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('num', models.IntegerField(unique=True, verbose_name=b'Account number')),
                ('name', models.CharField(max_length=100)),
                ('availableforinvoicing', models.BooleanField(default=False)),
                ('objectrequirement', models.IntegerField(default=0, verbose_name=b'Object requirements', choices=[(0, b'Optional'), (1, b'Required'), (2, b'Forbidden')])),
            ],
            options={
                'ordering': ('num',),
            },
        ),
        migrations.CreateModel(
            name='AccountClass',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('inbalance', models.BooleanField(default=False)),
                ('balancenegative', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('name',),
                'verbose_name': 'Account classes',
            },
        ),
        migrations.CreateModel(
            name='AccountGroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('foldable', models.BooleanField(default=False)),
                ('accountclass', models.ForeignKey(default=False, to='accounting.AccountClass')),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='IncomingBalance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('amount', models.DecimalField(max_digits=10, decimal_places=2, validators=[postgresqleu.accounting.models.nonzero_validator])),
                ('account', models.ForeignKey(to='accounting.Account', to_field=b'num')),
            ],
            options={
                'ordering': ('year__pk', 'account'),
            },
        ),
        migrations.CreateModel(
            name='JournalEntry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('seq', models.IntegerField()),
                ('date', models.DateField()),
                ('closed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='JournalItem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('amount', models.DecimalField(max_digits=10, decimal_places=2, validators=[postgresqleu.accounting.models.nonzero_validator])),
                ('description', models.CharField(max_length=200)),
                ('account', models.ForeignKey(to='accounting.Account', to_field=b'num')),
                ('journal', models.ForeignKey(to='accounting.JournalEntry')),
            ],
        ),
        migrations.CreateModel(
            name='JournalUrl',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.URLField()),
                ('journal', models.ForeignKey(to='accounting.JournalEntry')),
            ],
        ),
        migrations.CreateModel(
            name='Object',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=30)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='Year',
            fields=[
                ('year', models.IntegerField(serialize=False, primary_key=True)),
                ('isopen', models.BooleanField()),
            ],
            options={
                'ordering': ('-year',),
            },
        ),
        migrations.AddField(
            model_name='journalitem',
            name='object',
            field=models.ForeignKey(blank=True, to='accounting.Object', null=True),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='year',
            field=models.ForeignKey(to='accounting.Year'),
        ),
        migrations.AddField(
            model_name='incomingbalance',
            name='year',
            field=models.ForeignKey(to='accounting.Year'),
        ),
        migrations.AddField(
            model_name='account',
            name='group',
            field=models.ForeignKey(to='accounting.AccountGroup'),
        ),
        migrations.AlterUniqueTogether(
            name='journalentry',
            unique_together=set([('year', 'seq')]),
        ),
        migrations.AlterUniqueTogether(
            name='incomingbalance',
            unique_together=set([('year', 'account')]),
        ),
    ]
