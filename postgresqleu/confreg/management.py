from django.db.models import signals
from invoices.management import add_invoice_handler

def register_invoice_processor(app, created_models, verbosity=2, **kwargs):
	add_invoice_handler(app, 'confreg', 'confreg processor', 'postgresqleu.confreg.invoicehandler.InvoiceProcessor')

signals.post_syncdb.connect(register_invoice_processor)
