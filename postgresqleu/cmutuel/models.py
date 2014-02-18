from django.db import models

class CMutuelTransaction(models.Model):
	opdate = models.DateField(null=False, blank=False)
	valdate = models.DateField(null=False, blank=False)
	amount = models.DecimalField(max_digits=10, decimal_places=2, null=False, blank=False)
	description = models.CharField(max_length=300, null=False, blank=False)
	balance = models.DecimalField(max_digits=10, decimal_places=2, null=False, blank=False)

	sent = models.BooleanField(null=False, blank=False, default=False)

	class Meta:
		verbose_name='CMutuel Transaction'
		verbose_name_plural='CMutuel Transactions'
		ordering = ('-opdate',)

	def __unicode__(self):
		return "%s: %s" % (self.opdate, self.description)
