from django.conf import settings
from django.core import urlresolvers

from datetime import datetime

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice

from models import TransactionStatus, Report, AdyenLog

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
						  amount=notification.amount,
						  capturedat=None).save()

		# We can receive authorizations on non-primary Adyen merchant
		# accounts. This happens for example with payments from POS
		# terminals. In those cases, just send an email, and don't
		# try to match it to any invoices.
		# We still store and track the transaction.
		if notification.merchantAccountCode != settings.ADYEN_MERCHANTACCOUNT:
			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.ADYEN_NOTIFICATION_RECEIVER,
							 'Manual Adyen payment authorized',
							 "An Adyen payment of EUR%s was authorized on the Adyen platform.\nThis payment was not from the automated system, it was manually authorized, probably from a POS terminal.\nReference: %s\nAdyen reference: %s\nMerchant account: %s\n" % (notification.amount, notification.merchantReference, notification.pspReference, notification.merchantAccountCode))
			notification.confirmed = True
			notification.save()
			return

		# Process a payment on the primary account
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
			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.ADYEN_NOTIFICATION_RECEIVER,
							 'Adyen payment authorized',
							 "An Adyen payment of EUR%s with reference %s was authorized on the Adyen platform.\nInvoice: %s\nRecipient name: %s\nRecipient user: %s\nAdyen reference: %s\n" % (notification.amount, notification.merchantReference, invoice.title, invoice.recipient_name, invoice.recipient_email, notification.pspReference))

		except AdyenProcessingException, ex:
			# Generate an email telling us about this exception!
			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
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
						 "A creditcard authorization for %s on account %s has failed.\nThe reason given was:\n%s\n\nYou don't need to take any further action, nothing has been confirmed in the systems." % (
							 notification.merchantReference,
							 notification.merchantAccountCode,
							 notification.reason,
							 )
						 )
	notification.confirmed = True
	notification.save()

def process_capture(notification):
	if notification.success:
		# Successful capture, so we just set when the capture happened
		try:
			ts = TransactionStatus.objects.get(notification=notification)
			ts.capturedat = datetime.now()
			ts.save()
		except TransactionStatus.DoesNotExist:
			# We just ignore captures for non-existant transactions. This
			# seems to happen for example when a transaction is cancelled
			# on a POS terminal.
			pass
	else:
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.ADYEN_NOTIFICATION_RECEIVER,
						 'Unsuccessful adyen capture received',
						 "A creditcard capture for %s has failed.\nThe reason given was:\n%s\n\nYou want to investigate this since the payment was probably flagged as completed on authorization!\n" % (
							 notification.merchantReference,
							 notification.reason))
	# We confirm the notification even if we sent it, since there is not much more we can do
	notification.confirmed = True
	notification.save()

def process_new_report(notification):
	# Just store the fact that this report is available. We'll have an
	# asynchronous cronjob that downloads and processes the reports.
	Report(notification=notification, url=notification.reason, processedat=None).save()
	notification.confirmed=True
	notification.save()


def process_one_notification(notification):
	# Now do notification specific processing
	if not notification.live:
		# This one is in the test system only! So we just send
		# an email, because we're lazy
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.ADYEN_NOTIFICATION_RECEIVER,
						 'Received adyen notification type %s from the test system!' % notification.eventCode,
						 "An Adyen notification with live set to false has been received.\nYou probably want to check that out manually - it's in the database, but has received no further processing.\n",
			AdyenLog(pspReference=notification.pspReference, message='Received notification of type %s from the test system!' % notification.eventCode, error=True).save()
		)
		notification.confirmed = True
		notification.save()
	elif notification.eventCode == 'AUTHORISATION':
		process_authorization(notification)
	elif notification.eventCode == 'REPORT_AVAILABLE':
		process_new_report(notification)
	elif notification.eventCode == 'CAPTURE':
		process_capture(notification)
	elif notification.eventCode in ('UNSPECIFIED', ):
		# Any events that we just ignore still need to be flagged as
		# confirmed
		notification.confirmed = True
		notification.save()
		AdyenLog(pspReference=notification.pspReference, message='Received notification of type %s, ignored' % notification.eventCode).save()
	else:
		# Received an event that needs manual processing because we
		# don't know what to do with it. To make sure we can react
		# quickly to this, generate an immediate email for this.
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.ADYEN_NOTIFICATION_RECEIVER,
						 'Received unknown Adyen notification of type %s' % notification.eventCode,
						 "An unknown Adyen notification of type %s has been received.\n\nYou'll need to go process this one manually:\n%s" % (
							 notification.eventCode,
							 urlresolvers.reverse('admin:adyen_notification_change', args=(notification.id,)),
						 )
		)
		AdyenLog(pspReference=notification.pspReference, message='Received notification of unknown type %s' % notification.eventCode, error=True).save()

		# We specifically do *not* set the confirmed flag on this,
		# so that the cronjob will constantly bug the user about
		# unverified notifications.
