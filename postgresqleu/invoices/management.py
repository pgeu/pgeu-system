from django.db.models import signals
from invoices.models import InvoiceProcessor, InvoicePaymentMethod

def add_invoice_handler(app, model, name, classname=None):
		# Register the invoice processors, but only for the correct app
	if app.__name__ == 'postgresqleu.%s.models' % model:
		(i, created) = InvoiceProcessor.objects.get_or_create(processorname=name, classname=classname)
		if created:
			i.save()
			print "Added invoice processor for %s" % model

def register_invoice_payment_methods(app, created_models, verbosity=2, **kwargs):
	if app.__name__ == 'postgresqleu.invoices.models':
		(p, created) = InvoicePaymentMethod.objects.get_or_create(name='Paypal or creditcard', sortkey=100, classname='util.payment.paypal.Paypal')
		if created:
			p.save()
			print "Added payment processor for paypal"

		(p, created) = InvoicePaymentMethod.objects.get_or_create(name='Bank transfer', sortkey=200, classname='util.payment.banktransfer.Banktransfer', auto=False)
		if created:
			p.save()
			print "Added payment processor for bank transfer"

		(p, created) = InvoicePaymentMethod.objects.get_or_create(name='Credit card', sortkey=50, classname='util.payment.adyen.AdyenCreditcard', auto=True)
		if created:
			p.save()
			print "Added payment processor for adyen creditcard"

		(p, created) = InvoicePaymentMethod.objects.get_or_create(name='Dummy', sortkey=999, classname='util.payment.dummy.DummyPayment', auto=False, active=False)
		if created:
			p.save()
			print "Added payment processor for dummy payment"


signals.post_syncdb.connect(register_invoice_payment_methods)
