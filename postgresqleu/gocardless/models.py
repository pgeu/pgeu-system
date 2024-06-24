from django.db import models

from postgresqleu.invoices.models import InvoicePaymentMethod


class GocardlessTransaction(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)
    transactionid = models.CharField(max_length=200, blank=False, null=False)
    date = models.DateField(null=False, blank=False)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    paymentref = models.CharField(max_length=200, blank=True, null=False)
    transactionobject = models.JSONField(null=False, blank=False, default=dict)

    class Meta:
        unique_together = (
            ('transactionid', 'paymentmethod'),
        )
        ordering = ('-date', 'transactionid')

    def __str__(self):
        return self.transactionid
