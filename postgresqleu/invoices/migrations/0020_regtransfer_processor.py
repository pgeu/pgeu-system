# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def create_invoice_processors(apps, schema_editor):
    InvoiceProcessor = apps.get_model('invoices', 'InvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='confreg transfer processor',
                                           classname='postgresqleu.confreg.invoicehandler.TransferInvoiceProcessor')


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0019_invoice_extradescription'),
    ]

    operations = [
        migrations.RunPython(create_invoice_processors),
    ]
