from django.db import models

import cStringIO as StringIO
import base64

class Invoice(models.Model):
	invoicedate = models.DateTimeField(blank=False, null=False)
	duedate = models.DateField(blank=False, null=False)
	recipient = models.TextField(blank=False, null=False)
	pdf = models.TextField(blank=False, null=False) # BASE64-encoded :S
	totalamount = models.IntegerField(null=False, default=0)

	def __unicode__(self):
		return "Invoice %s (%s, due %s): EUR %s" % (
			self.id,
			self.invoicedate.strftime("%Y-%m-%d"),
			self.duedate.strftime("%Y-%m-%d"),
			self.totalamount,
			)

	def setpdf(self, binpdf):
		binpdf.seek(0)
		buf = StringIO.StringIO()
		base64.encode(binpdf, buf)
		self.pdf = buf.getvalue()

	def writepdf(self, outbuf):
		buf = StringIO.StringIO(self.pdf)
		base64.decode(buf, outbuf)
