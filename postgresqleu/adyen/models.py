from django.db import models

class RawNotification(models.Model):
	# This class contains the raw http POSTs of all notifications received
	# from Adyen. They will only end up unconfirmed here if sometihng
	# blows up badly.
	dat = models.DateTimeField(null=False, blank=False, auto_now_add=True, unique=True)
	contents = models.TextField(null=False, blank=False)
	confirmed = models.BooleanField(null=False, default=False)

	def __unicode__(self):
		return "%s" % self.dat

class Notification(models.Model):
	receivedat = models.DateTimeField(null=False, blank=False, auto_now_add=True, unique=True)
	rawnotification = models.ForeignKey(RawNotification, null=True, blank=True)
	eventDate = models.DateTimeField(null=False, blank=False)
	eventCode = models.CharField(max_length=100, null=False, blank=False)
	live = models.BooleanField(null=False)
	success = models.BooleanField(null=False)
	pspReference = models.CharField(max_length=100, null=False, blank=True)
	originalReference = models.CharField(max_length=100, null=False, blank=True)
	merchantReference = models.CharField(max_length=80, null=False, blank=True)
	merchantAccountCode = models.CharField(max_length=100, null=False, blank=True)
	paymentMethod = models.CharField(max_length=50, null=False, blank=True)
	# We ignore the operations field, we're never using it
	reason = models.CharField(max_length=1000, null=False, blank=True)
	amount = models.DecimalField(decimal_places=2, max_digits=20, null=True)

	confirmed = models.BooleanField(null=False, default=False)

	class Meta:
		unique_together = ('pspReference', 'eventCode', 'merchantAccountCode')

	def __unicode__(self):
		return "%s" % self.receivedat

class Report(models.Model):
	receivedat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	notification = models.ForeignKey(Notification, null=False, blank=False)
	url = models.CharField(max_length=1000, null=False, blank=False)
	downloadedat = models.DateTimeField(null=True, blank=True)
	contents = models.TextField(null=True, blank=True)
	processedat = models.DateTimeField(null=True, blank=True)

class TransactionStatus(models.Model):
	pspReference = models.CharField(max_length=100, null=False, blank=False, unique=True)
	notification = models.ForeignKey(Notification, null=False, blank=False)
	authorizedat = models.DateTimeField(null=False, blank=False)
	capturedat = models.DateTimeField(null=True, blank=True)
	settledat = models.DateTimeField(null=True, blank=True)
	amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)
	settledamount = models.DecimalField(null=True, decimal_places=2, max_digits=20)
	method = models.CharField(max_length=100, null=True, blank=True)
	notes = models.CharField(max_length=1000, null=True, blank=True)
	accounting_object = models.CharField(max_length=30, null=True, blank=True)

	def __unicode__(self):
		return self.pspReference

	class Meta:
		verbose_name_plural='Transaction statuses'

class Refund(models.Model):
	receivedat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	notification = models.ForeignKey(Notification, null=False, blank=False)
	transaction = models.OneToOneField(TransactionStatus)
	refund_amount = models.DecimalField(decimal_places=2, max_digits=20, null=False)

	def __unicode__(self):
		return unicode(self.refund_amount)

class ReturnAuthorizationStatus(models.Model):
	pspReference = models.CharField(max_length=100, null=False, blank=False, primary_key=True)
	seencount = models.IntegerField(null=False, default=0)


class AdyenLog(models.Model):
	timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	pspReference = models.CharField(max_length=100, null=False, blank=True)
	message = models.TextField(null=False, blank=False)
	error = models.BooleanField(null=False, blank=False, default=False)
	sent = models.BooleanField(null=False, blank=False, default=False)
