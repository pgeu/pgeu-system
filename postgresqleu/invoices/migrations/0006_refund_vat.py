# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0005_vat'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoicerefund',
            name='vatamount',
            field=models.DecimalField(default=0, max_digits=10, decimal_places=2),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='invoicerefund',
            name='vatrate',
            field=models.ForeignKey(to='invoices.VatRate', null=True),
        ),
        migrations.AlterField(
            model_name='invoicerefund',
            name='amount',
            field=models.DecimalField(max_digits=10, decimal_places=2),
        ),
    ]
