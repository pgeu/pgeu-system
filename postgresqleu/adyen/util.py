from django.conf import settings

from datetime import datetime

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice

from models import TransactionStatus, Report

# Internal exception class
class AdyenProcessingException(Exception):
	pass


###
# Process notifications of different types. Expects to be
# called within a transaction context already.
###
def process_authorization(notification):
	if notification.success:
		# This is a successful notification, so flag this invoice
		# as paid. We also create a TransactionStatus for it, so that
		# can validate that it goes from authorized->captured.
		TransactionStatus(pspReference=notification.pspReference,
						  notification=notification,
						  authorizedat=datetime.now(),
						  capturedat=None).save()
		manager = InvoiceManager()
		try:
			# Figure out the invoiceid
			if not notification.merchantReference.startswith('PGEU'):
				raise AdyenProcessingException('Merchant reference does not start with PGEU')
			invoiceid = int(notification.merchantReference[4:])

			# Get the actual invoice
			try:
				invoice = Invoice.objects.get(pk=invoiceid)
			except Invoice.DoesNotExist:
				raise AdyenProcessingException('Invoice with id %s does not exist' % invoiceid)

			def invoice_logger(msg):
				raise AdyenProcessingException('Invoice processing failed: %s', msg)

			manager.process_incoming_payment_for_invoice(invoice, notification.amount, 'Adyen id %s' % notification.pspReference, invoice_logger)

			# If nothing went wrong, then this invoice is now fully
			# flagged as paid in the system.
		except AdyenProcessingException, ex:
			# Generate an email telling us about this exception!
			send_simple_mail(settings.INOVICE_SENDER_EMAIL,
							 settings.ADYEN_NOTIFICATION_RECEIVER,
							 'Exception occured processing Adyen notification',
							 "An exception occured processing the notification for %s:\n\n%s\n" % (
								 notification.merchantReference,
								 ex)
						 )
			# We have stored the notification already, but we want
			# to make sure it's not *confirmed*. That way it'll keep
			# bugging the user. So, return here instead of confirming
			# it.
			return
	else:
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.ADYEN_NOTIFICATION_RECEIVER,
						 'Unsuccessful Adyen authorization received',
						 "A creditcard authorization for %s has failed.\nThe reason given was:\n%s\n\nYou don't need to take any further action, nothing has been confirmed in the systems." % (
							 notification.merchantReference,
							 notification.reason,
							 )
						 )
	notification.confirmed = True
	notification.save()


def process_new_report(notification):
	# Just store the fact that this report is available. We'll have an
	# asynchronous cronjob that downloads and processes the reports.
	Report(notification=notification, url=notification.reason, processedat=None).save()
	notification.confirmed=True
	notification.save()
