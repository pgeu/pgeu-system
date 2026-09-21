from django.db import models

from postgresqleu.invoices.models import InvoicePaymentMethod


class QontoTransaction(models.Model):
    qontoid = models.UUIDField(blank=False, null=False, unique=True)
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)
    datetime = models.DateTimeField(null=False, blank=False)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    operation_type = models.CharField(max_length=32, null=False, blank=False)
    paymentref = models.CharField(max_length=200, blank=True, null=False)

    counterpart_iban = models.CharField(max_length=100, blank=True, null=False)
    counterpart_bic = models.CharField(max_length=100, blank=True, null=False)

    class Meta:
        ordering = ('-datetime', )

    def __str__(self):
        return str(self.qontoid)
