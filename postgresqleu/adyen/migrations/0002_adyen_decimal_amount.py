# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adyen', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='amount',
            field=models.DecimalField(null=True, max_digits=20, decimal_places=2),
        ),
        migrations.AlterField(
            model_name='refund',
            name='refund_amount',
            field=models.DecimalField(max_digits=20, decimal_places=2),
        ),
        migrations.AlterField(
            model_name='transactionstatus',
            name='amount',
            field=models.DecimalField(max_digits=20, decimal_places=2),
        ),
    ]
