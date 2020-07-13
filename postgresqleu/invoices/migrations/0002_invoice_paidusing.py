# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0001_initial'),
        ('adyen', '0001_initial'),
        ('paypal', '0001_initial'),
        ('braintreepayment', '0001_initial')
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='paidusing',
            field=models.ForeignKey(related_name='paidusing', verbose_name='Payment method actually used', to='invoices.InvoicePaymentMethod', null=True, on_delete=models.CASCADE),
        ),
        migrations.RunSQL("UPDATE invoices_invoice SET paidusing_id=(SELECT id FROM invoices_invoicepaymentmethod WHERE classname='postgresqleu.util.payment.adyen.AdyenCreditcard') WHERE EXISTS (SELECT 1 FROM adyen_transactionstatus WHERE notes='PGEU' || invoices_invoice.id AND method != 'bankTransfer_IBAN')"),
        migrations.RunSQL("UPDATE invoices_invoice SET paidusing_id=(SELECT id FROM invoices_invoicepaymentmethod WHERE classname='postgresqleu.util.payment.adyen.AdyenBanktransfer') WHERE EXISTS (SELECT 1 FROM adyen_transactionstatus WHERE notes='PGEU' || invoices_invoice.id AND method = 'bankTransfer_IBAN')"),
        migrations.RunSQL("UPDATE invoices_invoice SET paidusing_id=(SELECT id FROM invoices_invoicepaymentmethod WHERE classname='postgresqleu.util.payment.paypal.Paypal') WHERE EXISTS (SELECT 1 FROM paypal_transactioninfo WHERE transtext LIKE 'PostgreSQL Europe Invoice #' || invoices_invoice.id || ' - %')"),
        # Our Braintree plugin doesn't keep enough details to do a direct matching, so we do
        # a fuzzy match based on our process taking less than 1 second. Which should be safe.
        migrations.RunSQL("UPDATE invoices_invoice SET paidusing_id=(SELECT id FROM invoices_invoicepaymentmethod WHERE classname='postgresqleu.util.payment.braintree.Braintree') WHERE EXISTS (SELECT 1 FROM braintreepayment_braintreetransaction WHERE (paidat-authorizedat) < '1 second'::interval AND (authorizedat-paidat) < '1 second'::interval AND total_amount=amount AND authorizedat IS NOT NULL AND paidat IS NOT NULL)")
    ]
