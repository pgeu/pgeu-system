from django.db.models import signals
from invoices.models import InvoiceProcessor, InvoicePaymentMethod

def add_invoice_handler(app, model, name, classname=None):
		# Register the invoice processors, but only for the correct app
	if app.__name__ == 'postgresqleu.%s.models' % model:
		(i, created) = InvoiceProcessor.objects.get_or_create(processorname=name, classname=classname)
		if created:
			i.save()
			print "Added invoice processor for %s" % model
