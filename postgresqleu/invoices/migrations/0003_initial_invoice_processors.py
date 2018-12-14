# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

def create_invoice_processors(apps, schema_editor):
    InvoiceProcessor = apps.get_model('invoices', 'InvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='confreg processor',
                                           classname='postgresqleu.confreg.invoicehandler.InvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='membership processor',
                                           classname='postgresqleu.membership.invoicehandler.InvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='confreg bulk processor',
                                           classname='postgresqleu.confreg.invoicehandler.BulkInvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='confsponsor processor',
                                           classname='postgresqleu.confsponsor.invoicehandler.InvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='confsponsor voucher processor',
                                           classname='postgresqleu.confsponsor.invoicehandler.VoucherInvoiceProcessor')

    InvoiceProcessor.objects.get_or_create(processorname='confreg addon processor',
                                           classname='postgresqleu.confreg.invoicehandler.AddonInvoiceProcessor')


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0002_invoice_paidusing'),
    ]

    operations = [
        migrations.RunPython(create_invoice_processors),
    ]
