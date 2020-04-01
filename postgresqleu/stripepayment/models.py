from django.db import models

from postgresqleu.invoices.models import InvoicePaymentMethod, InvoiceRefund


class StripeCheckout(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)
    createdat = models.DateTimeField(null=False, blank=False)
    invoiceid = models.IntegerField(null=False, blank=False, unique=True)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    sessionid = models.CharField(max_length=200, null=False, blank=False, unique=True)
    paymentintent = models.CharField(max_length=200, null=False, blank=False, unique=True)
    completedat = models.DateTimeField(null=True, blank=True)
    fee = models.DecimalField(decimal_places=2, max_digits=20, null=True)

    class Meta:
        ordering = ('-id', )


class StripeRefund(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)
    chargeid = models.CharField(max_length=200, null=False, blank=False)
    refundid = models.CharField(max_length=200, null=False, blank=False, unique=True)
    invoicerefundid = models.OneToOneField(InvoiceRefund, null=False, blank=False, unique=True, on_delete=models.CASCADE)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    completedat = models.DateTimeField(null=True, blank=True)


class StripePayout(models.Model):
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)
    payoutid = models.CharField(max_length=200, null=False, blank=False, unique=True)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    sentat = models.DateTimeField(null=False, blank=False)
    description = models.CharField(max_length=500, null=False, blank=False)


class ReturnAuthorizationStatus(models.Model):
    checkoutid = models.IntegerField(null=False, blank=False, primary_key=True)
    seencount = models.IntegerField(null=False, default=0)


class StripeLog(models.Model):
    timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    message = models.TextField(null=False, blank=False)
    error = models.BooleanField(null=False, blank=False, default=False)
    sent = models.BooleanField(null=False, blank=False, default=False)
    paymentmethod = models.ForeignKey(InvoicePaymentMethod, blank=False, null=False, on_delete=models.CASCADE)

    class Meta:
        ordering = ('-id', )
