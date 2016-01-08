# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('recipient_email', models.EmailField(max_length=254, blank=True)),
                ('recipient_name', models.CharField(max_length=100)),
                ('recipient_address', models.TextField()),
                ('recipient_secret', models.CharField(max_length=64, null=True, blank=True)),
                ('title', models.CharField(max_length=100, verbose_name=b'Invoice title')),
                ('invoicedate', models.DateTimeField()),
                ('duedate', models.DateTimeField()),
                ('canceltime', models.DateTimeField(help_text=b'Invoice will automatically be canceled at this time', null=True, blank=True)),
                ('total_amount', models.IntegerField()),
                ('finalized', models.BooleanField(default=False, help_text=b'Invoice is finalized, should not ever be changed again')),
                ('deleted', models.BooleanField(default=False, help_text=b'This invoice has been deleted')),
                ('deletion_reason', models.CharField(default=b'', help_text=b'Reason for deletion of invoice', max_length=500, blank=True)),
                ('refunded', models.BooleanField(default=False, help_text=b'This invoice has been refunded')),
                ('refund_reason', models.CharField(default=b'', help_text=b'Reason for refunding of invoice', max_length=500, blank=True)),
                ('pdf_invoice', models.TextField(blank=True)),
                ('processorid', models.IntegerField(null=True, blank=True)),
                ('bankinfo', models.BooleanField(default=True, verbose_name=b'Include bank details on invoice')),
                ('paidat', models.DateTimeField(null=True, blank=True)),
                ('paymentdetails', models.CharField(max_length=100, blank=True)),
                ('remindersent', models.DateTimeField(null=True, verbose_name=b'Automatic reminder sent at', blank=True)),
                ('pdf_receipt', models.TextField(blank=True)),
                ('accounting_account', models.IntegerField(null=True, verbose_name=b'Accounting account', blank=True)),
                ('accounting_object', models.CharField(max_length=30, null=True, verbose_name=b'Accounting object', blank=True)),
            ],
            options={
                'ordering': ('-id',),
            },
        ),
        migrations.CreateModel(
            name='InvoiceHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time', models.DateTimeField(auto_now_add=True)),
                ('txt', models.CharField(max_length=100)),
                ('invoice', models.ForeignKey(to='invoices.Invoice')),
            ],
            options={
                'ordering': ['time'],
            },
        ),
        migrations.CreateModel(
            name='InvoiceLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('message', models.TextField()),
                ('sent', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='InvoicePaymentMethod',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('active', models.BooleanField(default=True)),
                ('sortkey', models.IntegerField(default=100)),
                ('internaldescription', models.CharField(max_length=100, blank=True)),
                ('classname', models.CharField(unique=True, max_length=200)),
                ('auto', models.BooleanField(default=True, verbose_name=b'Used by automatically generated invoices')),
            ],
            options={
                'ordering': ['sortkey'],
            },
        ),
        migrations.CreateModel(
            name='InvoiceProcessor',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('processorname', models.CharField(unique=True, max_length=50)),
                ('classname', models.CharField(max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='InvoiceRow',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('rowtext', models.CharField(max_length=100, verbose_name=b'Text')),
                ('rowcount', models.IntegerField(default=1, verbose_name=b'Count')),
                ('rowamount', models.IntegerField(default=0, verbose_name=b'Amount per item')),
                ('invoice', models.ForeignKey(to='invoices.Invoice')),
            ],
        ),
        migrations.AddField(
            model_name='invoice',
            name='allowedmethods',
            field=models.ManyToManyField(to='invoices.InvoicePaymentMethod', verbose_name=b'Allowed payment methods', blank=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='processor',
            field=models.ForeignKey(blank=True, to='invoices.InvoiceProcessor', null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='recipient_user',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
    ]
