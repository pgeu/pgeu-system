from django.db import models

from postgresqleu.invoices.models import InvoicePaymentMethod


class TransferwiseTransaction(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False)
    twreference = models.CharField(max_length=100, blank=False, null=False)
    datetime = models.DateTimeField(null=False, blank=False)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    feeamount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    transtype = models.CharField(max_length=32, blank=False, null=False)
    paymentref = models.CharField(max_length=200, blank=True, null=False)
    fulldescription = models.CharField(max_length=500, blank=True, null=False)
    counterpart_name = models.CharField(max_length=100, blank=True, null=False)
    counterpart_account = models.CharField(max_length=100, blank=True, null=False)
    counterpart_valid_iban = models.BooleanField(null=False, default=False)

    class Meta:
        unique_together = (
            ('twreference', 'paymentmethod'),
        )
        ordering = ('-datetime', )

    def __str__(self):
        return self.twreference


class TransferwiseRefund(models.Model):
    origtransaction = models.ForeignKey(TransferwiseTransaction, blank=False, null=False, related_name='refund_orig')
    refundtransaction = models.OneToOneField(TransferwiseTransaction, blank=True, null=True, related_name='refund_refund', unique=True)
    refundid = models.BigIntegerField(null=False, unique=True)
    uuid = models.UUIDField(blank=False, null=False, unique=True)
    transferid = models.BigIntegerField(null=False, unique=True)
    accid = models.BigIntegerField(null=True)
    quoteid = models.BigIntegerField(null=True)
    createdat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    completedat = models.DateTimeField(null=True, blank=True)


class TransferwisePayout(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    reference = models.CharField(max_length=100, null=False, blank=False)
    uuid = models.UUIDField(blank=False, null=False, unique=True)
    transferid = models.BigIntegerField(null=True)
    accid = models.BigIntegerField(null=True)
    quoteid = models.BigIntegerField(null=True)
    createdat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    sentat = models.DateTimeField(null=True, blank=True)
    completedat = models.DateTimeField(null=True, blank=True)
