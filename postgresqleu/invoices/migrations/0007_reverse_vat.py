# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0006_refund_vat'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='reverse_vat',
            field=models.BooleanField(default=False, help_text=b'Invoice is subject to EU reverse VAT'),
        ),
    ]
