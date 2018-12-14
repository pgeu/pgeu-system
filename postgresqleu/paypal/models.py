from django.db import models

from datetime import datetime


class SourceAccount(models.Model):
    accountname = models.CharField(max_length=16, null=False, blank=False)
    lastsync = models.DateTimeField(null=False, blank=False, default=datetime(2009, 1, 1))

    def __unicode__(self):
        return self.accountname


class TransactionInfo(models.Model):
    paypaltransid = models.CharField(max_length=20, null=False, blank=False, unique=True)
    timestamp = models.DateTimeField(null=False, blank=False)
    sourceaccount = models.ForeignKey(SourceAccount, null=False, blank=False, on_delete=models.CASCADE)
    sender = models.CharField(max_length=200, null=False, blank=False)
    sendername = models.CharField(max_length=200, null=False, blank=False)
    amount = models.DecimalField(decimal_places=2, max_digits=10, null=False, blank=False)
    fee = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    transtext = models.CharField(max_length=1000, null=False, blank=False)
    matched = models.BooleanField(null=False, blank=False)
    matchinfo = models.CharField(max_length=1000, null=True, blank=True)

    def setmatched(self, msg):
        self.matched = True
        self.matchinfo = msg
        self.save()


class ErrorLog(models.Model):
    timestamp = models.DateTimeField(null=False, blank=False)
    message = models.TextField(null=False, blank=False)
    sent = models.BooleanField(null=False, blank=False)
