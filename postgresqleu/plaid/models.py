from django.db import models

from postgresqleu.invoices.models import InvoicePaymentMethod


class PlaidTransaction(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)
    transactionid = models.CharField(max_length=100, blank=False, null=False)
    datetime = models.DateTimeField(null=False, blank=False)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    paymentref = models.CharField(max_length=200, blank=True, null=False)
    transactionobject = models.JSONField(null=False, blank=False, default=dict)

    class Meta:
        unique_together = (
            ('transactionid', 'paymentmethod'),
        )
        ordering = ('-datetime', )

    def __str__(self):
        return self.transactionid


class PlaidWebhookData(models.Model):
    datetime = models.DateTimeField(null=False, blank=False, auto_now_add=True, db_index=True)
    source = models.GenericIPAddressField(null=True, blank=True)
    signature = models.CharField(max_length=1000, null=False, blank=False)
    hook_code = models.CharField(max_length=200, null=False, blank=False)
    contents = models.JSONField(null=False, blank=False, default=dict)

    class Meta:
        ordering = ('-datetime', )
