# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0001_initial'),
        ('invoices', '0004_refund_tracking'),
    ]

    operations = [
        migrations.CreateModel(
            name='VatRate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('shortname', models.CharField(max_length=16, verbose_name='Short name')),
                ('vatpercent', models.IntegerField(default=0, verbose_name='VAT percentage', validators=[django.core.validators.MaxValueValidator(100), django.core.validators.MinValueValidator(0)])),
                ('vataccount', models.ForeignKey(to='accounting.Account', on_delete=models.CASCADE, verbose_name='VAT account')),
            ],
        ),
        migrations.AddField(
            model_name='invoice',
            name='total_vat',
            field=models.DecimalField(default=0, max_digits=10, decimal_places=2),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='total_amount',
            field=models.DecimalField(max_digits=10, decimal_places=2),
        ),
        migrations.AlterField(
            model_name='invoicerow',
            name='rowamount',
            field=models.DecimalField(default=0, verbose_name='Amount per item (ex VAT)', max_digits=10, decimal_places=2),
        ),
        migrations.AddField(
            model_name='invoicerow',
            name='vatrate',
            field=models.ForeignKey(to='invoices.VatRate', null=True, on_delete=models.CASCADE),
        ),
    ]
