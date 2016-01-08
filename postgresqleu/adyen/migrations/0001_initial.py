# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AdyenLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('pspReference', models.CharField(max_length=100, blank=True)),
                ('message', models.TextField()),
                ('error', models.BooleanField(default=False)),
                ('sent', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('receivedat', models.DateTimeField(auto_now_add=True, unique=True)),
                ('eventDate', models.DateTimeField()),
                ('eventCode', models.CharField(max_length=100)),
                ('live', models.BooleanField()),
                ('success', models.BooleanField()),
                ('pspReference', models.CharField(max_length=100, blank=True)),
                ('originalReference', models.CharField(max_length=100, blank=True)),
                ('merchantReference', models.CharField(max_length=80, blank=True)),
                ('merchantAccountCode', models.CharField(max_length=100, blank=True)),
                ('paymentMethod', models.CharField(max_length=50, blank=True)),
                ('reason', models.CharField(max_length=1000, blank=True)),
                ('amount', models.IntegerField(null=True)),
                ('confirmed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='RawNotification',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('dat', models.DateTimeField(auto_now_add=True, unique=True)),
                ('contents', models.TextField()),
                ('confirmed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='Refund',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('receivedat', models.DateTimeField(auto_now_add=True)),
                ('refund_amount', models.IntegerField()),
                ('notification', models.ForeignKey(to='adyen.Notification')),
            ],
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('receivedat', models.DateTimeField(auto_now_add=True)),
                ('url', models.CharField(max_length=1000)),
                ('downloadedat', models.DateTimeField(null=True, blank=True)),
                ('contents', models.TextField(null=True, blank=True)),
                ('processedat', models.DateTimeField(null=True, blank=True)),
                ('notification', models.ForeignKey(to='adyen.Notification')),
            ],
        ),
        migrations.CreateModel(
            name='ReturnAuthorizationStatus',
            fields=[
                ('pspReference', models.CharField(max_length=100, serialize=False, primary_key=True)),
                ('seencount', models.IntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='TransactionStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('pspReference', models.CharField(unique=True, max_length=100)),
                ('authorizedat', models.DateTimeField()),
                ('capturedat', models.DateTimeField(null=True, blank=True)),
                ('settledat', models.DateTimeField(null=True, blank=True)),
                ('amount', models.IntegerField()),
                ('settledamount', models.DecimalField(null=True, max_digits=20, decimal_places=2)),
                ('method', models.CharField(max_length=100, null=True, blank=True)),
                ('notes', models.CharField(max_length=1000, null=True, blank=True)),
                ('accounting_object', models.CharField(max_length=30, null=True, blank=True)),
                ('notification', models.ForeignKey(to='adyen.Notification')),
            ],
            options={
                'verbose_name_plural': 'Transaction statuses',
            },
        ),
        migrations.AddField(
            model_name='refund',
            name='transaction',
            field=models.OneToOneField(to='adyen.TransactionStatus'),
        ),
        migrations.AddField(
            model_name='notification',
            name='rawnotification',
            field=models.ForeignKey(blank=True, to='adyen.RawNotification', null=True),
        ),
        migrations.AlterUniqueTogether(
            name='notification',
            unique_together=set([('pspReference', 'eventCode', 'merchantAccountCode')]),
        ),
    ]
