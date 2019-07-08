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
                ('num', models.IntegerField(unique=True, verbose_name='Account number')),
                ('name', models.CharField(max_length=100)),
                ('availableforinvoicing', models.BooleanField(default=False, verbose_name='Available for invoicing', help_text='List this account in the dropdown when creating a manual invoice')),
                ('objectrequirement', models.IntegerField(default=0, verbose_name='Object required', choices=[(0, 'Optional'), (1, 'Required'), (2, 'Forbidden')], help_text='Require an object to be specified when using this account')),
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
                ('inbalance', models.BooleanField(default=False, verbose_name='In balance', help_text='Is this account class listed in the balance report (instead of results report)')),
                ('balancenegative', models.BooleanField(default=False, verbose_name='Balance negative', help_text='Should the sign of the balance of this account be reversed in the report')),
            ],
            options={
                'ordering': ('name',),
                'verbose_name': 'Account class',
                'verbose_name_plural': 'Account classes',
            },
        ),
        migrations.CreateModel(
            name='AccountGroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('foldable', models.BooleanField(default=False, help_text='If this account is alone in the group having values, fold it into a single line and rmeove the group header/footer')),
                ('accountclass', models.ForeignKey(default=False, to='accounting.AccountClass', on_delete=models.CASCADE, verbose_name='Account class')),
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
                ('account', models.ForeignKey(to='accounting.Account', to_field='num', on_delete=models.CASCADE)),
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
                ('account', models.ForeignKey(to='accounting.Account', to_field='num', on_delete=models.CASCADE)),
                ('journal', models.ForeignKey(to='accounting.JournalEntry', on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='JournalUrl',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.URLField()),
                ('journal', models.ForeignKey(to='accounting.JournalEntry', on_delete=models.CASCADE)),
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
                'verbose_name': 'Accounting object'
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
            field=models.ForeignKey(blank=True, to='accounting.Object', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='year',
            field=models.ForeignKey(to='accounting.Year', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='incomingbalance',
            name='year',
            field=models.ForeignKey(to='accounting.Year', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='account',
            name='group',
            field=models.ForeignKey(to='accounting.AccountGroup', on_delete=models.CASCADE),
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
