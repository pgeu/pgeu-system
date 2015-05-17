from django.db.models import signals
from invoices.management import add_invoice_handler

def register_invoice_processor(app, created_models, verbosity=2, **kwargs):
	add_invoice_handler(app, 'confsponsor', 'confsponsor processor', 'postgresqleu.confsponsor.invoicehandler.InvoiceProcessor')
	add_invoice_handler(app, 'confsponsor', 'confsponsor voucher processor', 'postgresqleu.confsponsor.invoicehandler.VoucherInvoiceProcessor')

signals.post_syncdb.connect(register_invoice_processor)
