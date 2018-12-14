from django.db import models

class TrustlyTransaction(models.Model):
    createdat = models.DateTimeField(null=False, blank=False)
    pendingat = models.DateTimeField(null=True, blank=True)
    completedat = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
    invoiceid = models.IntegerField(null=False, blank=False)
    redirecturl = models.CharField(max_length=2000, null=False, blank=False)
    orderid = models.BigIntegerField(null=False, blank=False)

    def __unicode__(self):
        return "%s" % self.orderid

class TrustlyRawNotification(models.Model):
    dat = models.DateTimeField(null=False, blank=False, auto_now_add=True, unique=True)
    contents = models.TextField(null=False, blank=False)
    confirmed = models.BooleanField(null=False, default=False)

    def __unicode__(self):
        return "%s" % self.dat

class TrustlyNotification(models.Model):
    receivedat = models.DateTimeField(null=False, blank=False, auto_now_add=True, unique=True)
    rawnotification = models.ForeignKey(TrustlyRawNotification, null=True, blank=True, on_delete=models.CASCADE)
    notificationid = models.BigIntegerField(null=False, blank=False)
    orderid = models.BigIntegerField(null=False, blank=False)
    method = models.CharField(max_length=80, null=False, blank=False)
    amount = models.DecimalField(decimal_places=2, max_digits=20, null=True, blank=True)
    messageid = models.CharField(max_length=80, null=False, blank=False)

    confirmed = models.BooleanField(null=False, default=False)

    def __unicode__(self):
        return "%s" % self.receivedat

class TrustlyLog(models.Model):
    timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    message = models.TextField(null=False, blank=False)
    error = models.BooleanField(null=False, blank=False, default=False)
    sent = models.BooleanField(null=False, blank=False, default=False)

class ReturnAuthorizationStatus(models.Model):
    orderid = models.BigIntegerField(null=False, blank=False, primary_key=True)
    seencount = models.IntegerField(null=False, default=0)
