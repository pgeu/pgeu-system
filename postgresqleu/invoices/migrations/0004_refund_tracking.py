# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0003_initial_invoice_processors'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvoiceRefund',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('reason', models.CharField(default=b'', help_text=b'Reason for refunding of invoice', max_length=500, blank=True)),
                ('amount', models.IntegerField()),
                ('registered', models.DateTimeField(auto_now_add=True)),
                ('issued', models.DateTimeField(null=True, blank=True)),
                ('completed', models.DateTimeField(null=True, blank=True)),
                ('payment_reference', models.CharField(help_text=b'Reference in payment system, depending on system used for invoice.', max_length=100, blank=True)),
                ('refund_pdf', models.TextField(blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='invoice',
            name='refund',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, blank=True, to='invoices.InvoiceRefund'),
        ),
		migrations.RunSQL("INSERT INTO invoices_invoicerefund (reason, amount, registered, issued, completed, payment_reference, refund_pdf) SELECT refund_reason, total_amount, paidat, paidat, paidat, 'MIGRATED_' || id, '' FROM invoices_invoice WHERE refunded"),
		migrations.RunSQL("UPDATE invoices_invoice SET refund_id=invoices_invoicerefund.id FROM invoices_invoicerefund WHERE invoices_invoicerefund.payment_reference='MIGRATED_'||invoices_invoice.id"),
        migrations.RemoveField(
            model_name='invoice',
            name='refund_reason',
        ),
        migrations.RemoveField(
            model_name='invoice',
            name='refunded',
        ),
        migrations.AlterField(
            model_name='invoice',
            name='paidusing',
            field=models.ForeignKey(related_name='paidusing', verbose_name=b'Payment method actually used', blank=True, to='invoices.InvoicePaymentMethod', null=True),
        ),
    ]
