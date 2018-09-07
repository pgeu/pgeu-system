# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ReturnAuthorizationStatus',
            fields=[
                ('orderid', models.BigIntegerField(serialize=False, primary_key=True)),
                ('seencount', models.IntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='TrustlyLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('message', models.TextField()),
                ('error', models.BooleanField(default=False)),
                ('sent', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='TrustlyNotification',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('receivedat', models.DateTimeField(auto_now_add=True, unique=True)),
                ('notificationid', models.BigIntegerField()),
                ('orderid', models.BigIntegerField()),
                ('method', models.CharField(max_length=80)),
                ('amount', models.DecimalField(max_digits=20, decimal_places=2)),
                ('messageid', models.CharField(max_length=80)),
                ('confirmed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='TrustlyRawNotification',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('dat', models.DateTimeField(auto_now_add=True, unique=True)),
                ('contents', models.TextField()),
                ('confirmed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='TrustlyTransaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('createdat', models.DateTimeField()),
                ('pendingat', models.DateTimeField(null=True, blank=True)),
                ('completedat', models.DateTimeField(null=True, blank=True)),
                ('amount', models.DecimalField(max_digits=20, decimal_places=2)),
                ('invoiceid', models.IntegerField()),
                ('redirecturl', models.CharField(max_length=2000)),
                ('orderid', models.BigIntegerField()),
            ],
        ),
        migrations.AddField(
            model_name='trustlynotification',
            name='rawnotification',
            field=models.ForeignKey(blank=True, to='trustlypayment.TrustlyRawNotification', null=True, on_delete=models.CASCADE),
        ),
    ]
