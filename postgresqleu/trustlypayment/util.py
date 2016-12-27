from django.conf import settings
from django.db import transaction

from datetime import datetime
from decimal import Decimal

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod

from api import TrustlyWrapper, TrustlyException
from models import TrustlyTransaction, TrustlyLog
from models import TrustlyNotification, TrustlyRawNotification

# Django intgrated wrapper for the trustly API

class Trustly(TrustlyWrapper):
	def __init__(self):
		super(Trustly, self).__init__(settings.TRUSTLY_APIBASE,
									  settings.TRUSTLY_USER,
									  settings.TRUSTLY_PASSWORD,
									  settings.TRUSTLY_PRIVATE_KEY,
									  settings.TRUSTLY_PUBLIC_KEY,
									  '{0}/trustly_notification/'.format(settings.SITEBASE),
									  settings.CURRENCY_ABBREV,
									  getattr(settings, 'TRUSTLY_HOLD_NOTIFICATIONS', False),
									  )

	def process_raw_trustly_notification(self, raw):
		(uuid, method, data) = self.parse_notification(raw.contents)
		if not data:
			return (False, uuid, method)

		n = None
		with transaction.atomic():
			# Find if we have already seen this guy
			try:
				TrustlyNotification.objects.get(notificationid=data['notificationid'])
				# If it's found, then we're happy, so keep on smiling. Flag this one as
				# confirmed as well.
				raw.confirmed = True
				raw.save()
				return (True, uuid, method)
			except TrustlyNotification.DoesNotExist:
				pass

			n = TrustlyNotification(
				receivedat=datetime.now(),
				rawnotification=raw,
				method=method,
				notificationid=data['notificationid'],
				orderid=data['orderid'],
				amount=data.has_key('amount') and Decimal(data['amount']) or None,
				messageid=data['messageid'],
			)
			n.save()
			raw.confirmed=True
			raw.save()

		# Raw is confirmed, but parsed one is still pending. So handle that one.
		try:
			self.process_notification(n)
		except Exception, e:
			self.log_and_email("Exception processing notification {0}: {1}".format(n.id, e))

		# If we somehow failed to handle at this level, we still flag things as ok to
		# Trustly, and deal with it ourselves.
		# Notifications can always be re-parsed
		return (True, uuid, method)

	def log_and_email(self, message):
		TrustlyLog(message=message, error=True).save()

		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.TRUSTLY_NOTIFICATION_RECEIVER,
						 "Trustly payment error",
						 u"A trustly payment failed with the error:\n\n{0}".format(message),
						 )

	@transaction.atomic
	def process_notification(self, notification):
		if notification.method in ('pending', 'credit'):
			# Find the appropriate transaction
			try:
				trans = TrustlyTransaction.objects.get(orderid=notification.orderid)
			except TrustlyTransaction.DoesNotExist:
				self.log_and_email("Transaction {0} for notification {1} not found!".format(notification.orderid, notification.id))
				return False
			if trans.amount != notification.amount:
				self.log_and_email("Notification {0} for transaction {1} has invalid amount ({2} should be {3})!".format(notification.id, notification.orderid, notification.amount, trans.amount))
				return False

			if notification.method == 'pending':
				# Pending is just an incremental state, so we collect it but don't do anything with
				# it.
				if not trans.pendingat:
					trans.pendingat = datetime.now()
					trans.save()
			else:
				# Credit! The payment is completed!
				if not trans.pendingat:
					# We set pending in case it never showed up
					trans.pendingat = datetime.now()
				if trans.completedat:
					self.log_and_email("Duplicate completed notification ({0}) received for transaction {1}!".format(notification.id, notification.orderid))
					return False

				trans.completedat = datetime.now()
				try:
					self.process_completed_payment(trans)
				except TrustlyException, e:
					self.log_and_email(e)
					return False
				trans.save()
				notification.confirmed=True
				notification.save()
				return True
		elif notification.method == 'cancel':
			try:
				trans = TrustlyTransaction.objects.get(orderid=notification.orderid)
			except TrustlyTransaction.DoesNotExist:
				TrustlyLog("Abandoned transaction {0} canceled from notification".format(notification.orderid))
				return False
			if trans.pendingat:
				self.log_and_email("Transaction {0} canceled by notification {1} but already in progress. Ignoring cancel!".format(notification.orderid, notification.id))
				return False
			TrustlyLog(message='Transaction {0} canceled from notification'.format(notification.orderid)).save()
			trans.delete()
			notification.confirmed = True
			notification.save()
			return True
		else:
			self.log_and_email("Unknown noficiation type '{0}' in notification {1}".format(notification.method, notification.id))
			return False

		# Can't reach here
		return False

	def process_completed_payment(self, trans):
		manager = InvoiceManager()
		try:
			invoice = Invoice.objects.get(pk=trans.invoiceid)
		except Invoice.DoesNotExist:
			raise TrustlyException("Received Trustly notification for non-existing invoice id {0}".format(trans.invoiceid))

		def invoice_logger(msg):
			raise TrustlyException("Trustly invoice processing failed: {0}".format(msg))

		method = InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.trustly.TrustlyPayment')
		manager.process_incoming_payment_for_invoice(invoice,
													 trans.amount,
													 'Trustly id {0}'.format(trans.id),
													 0, #XXX: we pay zero now, but should perhaps support fees?
													 settings.ACCOUNTING_TRUSTLY_ACCOUNT,
													 0, #XXX: if supporting fees, support fee account
													 [],
													 invoice_logger,
													 method)
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.TRUSTLY_NOTIFICATION_RECEIVER,
						 "Trustly payment completed",
						 "A Trustly payment of {0}{1} for invoice {2} was completed on the Trustly platform.\n\nInvoice: {3}\nRecipient name: {4}\nRecipient email: {5}\n".format(settings.CURRENCY_ABBREV, trans.amount, invoice.id, invoice.title, invoice.recipient_name, invoice.recipient_email),
						 )
