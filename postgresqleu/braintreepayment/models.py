from django.db import models


class BraintreeTransaction(models.Model):
    transid = models.CharField(max_length=100, null=False, blank=False, unique=True)
    authorizedat = models.DateTimeField(null=False, blank=False)
    settledat = models.DateTimeField(null=True, blank=True)
    disbursedat = models.DateTimeField(null=True, blank=True)
    amount = models.IntegerField(null=False)
    disbursedamount = models.DecimalField(null=True, blank=True, decimal_places=2, max_digits=20)
    method = models.CharField(max_length=100, null=True, blank=True)
    accounting_object = models.CharField(max_length=30, null=True, blank=True)

    def __unicode__(self):
        return self.transid


class BraintreeLog(models.Model):
    timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    transid = models.CharField(max_length=100, null=False, blank=False)
    message = models.TextField(null=False, blank=False)
    error = models.BooleanField(null=False, blank=False, default=False)
    sent = models.BooleanField(null=False, blank=False, default=False)
