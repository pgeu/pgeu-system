from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.db import transaction
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from django.core import urlresolvers

import base64

from postgresqleu.util.decorators import ssl_required
from postgresqleu.util.payment.adyen import calculate_signature
from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.mailqueue.util import send_simple_mail

from models import Notification, RawNotification, AdyenLog, ReturnAuthorizationStatus
from util import process_authorization, process_new_report

@ssl_required
@transaction.commit_on_success
def adyen_return_handler(request):
	sig = calculate_signature(request.GET, ('authResult', 'pspReference', 'merchantReference', 'skinCode', 'merchantReturnData'))

	if sig != request.GET['merchantSig']:
		return render_to_response('adyen/sigerror.html',
								  context_instance=RequestContext(request))

	# We're going to need the invoice for pretty much everything,
	# so attempt to find it.
	if request.GET['merchantReturnData'] != request.GET['merchantReference'] or not request.GET['merchantReturnData'].startswith('PGEU'):
		AdyenLog(pspReference='', message='Return handler received invalid reference %s/%s' % (request.GET['merchantReturnData'], request.GET['merchantReference']), error=True).save()
		return render_to_response('adyen/invalidreference.html', {
			'reference': "%s//%s" % (request.GET['merchantReturnData'], request.GET['merchantReference']),
		}, context_instance=RequestContext(request))

	invoiceid = int(request.GET['merchantReturnData'][4:])
	try:
		invoice = Invoice.objects.get(pk=invoiceid)
	except Invoice.DoesNotExist:
		AdyenLog(pspReference='', message='Return handler could not find invoice for reference %s' % request.GET['merchantReturnData'], error=True).save()
		return render_to_response('adyen/invalidreference.html', {
			'reference': request.GET['merchantReturnData'],
		}, context_instance=RequestContext(request))
	manager = InvoiceManager()
	if invoice.processor:
		processor = manager.get_invoice_processor(invoice)
		returnurl = processor.get_return_url(invoice)
	else:
		if invoice.recipient_user:
			returnurl = "%s/invoices/%s/" % (settings.SITEBASE_SSL, invoice.pk)
		else:
			returnurl = "%s/invoices/%s/%s/" % (settings.SITEBASE_SSL, invoice.pk, invoice.recipient_secret)

	AdyenLog(pspReference='', message='Return handler received %s result for %s' % (request.GET['authResult'], request.GET['merchantReturnData']), error=False).save()
	if request.GET['authResult'] == 'REFUSED':
		return render_to_response('adyen/refused.html', {
			'url': returnurl,
			}, context_instance=RequestContext(request))
	elif request.GET['authResult'] == 'CANCELLED':
		return HttpResponseRedirect(returnurl)
	elif request.GET['authResult'] == 'ERROR':
		return render_to_response('adyen/transerror.html', {
			'url': returnurl,
			}, context_instance=RequestContext(request))
	elif request.GET['authResult'] == 'PENDING':
		return render_to_response('adyen/pending.html', {
			'url': returnurl,
			}, context_instance=RequestContext(request))
	elif request.GET['authResult'] == 'AUTHORISED':
		# NOTE! Adyen strongly recommends not reacting on
		# authorized values, but deal with them from the
		# notifications instead. So we'll do that.
		# However, if we reach this point and it's actually
		# already dealt with by the notification arriving
		# asynchronously, redirect the user properly.
		if invoice.paidat:
			# Yup, it's paid, so send the user off to the page
			# that they came from.
			return HttpResponseRedirect(returnurl)

		# Show the user a pending message. The refresh time is dependent
		# on how many times we've seen this one before.
		status, created = ReturnAuthorizationStatus.objects.get_or_create(pspReference=request.GET['pspReference'])
		status.seencount += 1
		status.save()
		return render_to_response('adyen/authorized.html', {
			'refresh': 3**status.seencount,
			'url': returnurl,
			}, context_instance=RequestContext(request))
	else:
		return render_to_response('adyen/invalidresult.html', {
			'result': request.GET['authResult'],
			}, context_instance=RequestContext(request))


@ssl_required
def adyen_notify_handler(request):
	# Handle asynchronous notifications from the Adyen payment platform

	# Authenticate with HTTP BASIC
	if not 'HTTP_AUTHORIZATION' in request.META:
		raise Exception('Adyen notification received without authentication')
	auth = request.META['HTTP_AUTHORIZATION'].split()
	if len(auth) != 2:
		raise Exception('Adyen notification received with invalid length authentication')
	if auth[0].lower() != 'basic':
		raise Exception('Adyen notification received with invalid authentication type')
	user, pwd = base64.b64decode(auth[1]).split(':')
	if user != settings.ADYEN_NOTIFY_USER or pwd != settings.ADYEN_NOTIFY_PASSWORD:
		return HttpResponseForbidden('Invalid username or password')

	# Ok, we have authentication. All our data is now available in
	# request.POST

	# Store the raw notification at this point, so we have it around in
	# case something breaks in a way we couldn't handle
	raw = RawNotification(contents=request.body)
	raw.save()

	# Now open a transaction for actually processing what we get
	with transaction.commit_on_success():
		# Set it to confirmed - if we were unable to process the RAW one,
		# this will be rolled back by the transaction, and that's the only
		# thing that htis flag means. Anything else is handled by the
		# regular notification.
		raw.confirmed = True
		raw.save()

		# Have we already seen this notification before?
		notlist = list(Notification.objects.filter(pspReference=request.POST['pspReference'], eventCode=request.POST['eventCode']))
		if len(notlist) == 1:
			# Found it before!
			notification = notlist[0]

			# According to Adyen integration manual, the only case when
			# we need to process this is when it goes from
			# success=False -> success=True.
			if not notification.success and request.POST['success'] == 'true':
				# We'll implement this one later, but for now trigger a
				# manual email so we don't loose things.
				send_simple_mail(settings.INVOICE_SENDER_EMAIL,
								 settings.ADYEN_NOTIFICATION_RECEIVER,
								 'Received adyen notification type %s that went from failure to success!' % notification.eventCode,
							 "An Adyen notification that went from failure to success has been received.\nThe system doesn't know how to handle this yet, so you'll need to go take a manual look!\n",
							 )
				AdyenLog(pspReference=notification.pspReference, message='Received success->fail notification of type %s, unhandled' % notification.eventCode, error=True).save()
			else:
				AdyenLog(pspReference=notification.pspReference, message='Received duplicate %s notification' % notification.eventCode).save()
				# Don't actually do any processing here either
		else:
			# Not found, so create
			notification = Notification()
			notification.eventDate = request.POST['eventDate']
			notification.eventCode = request.POST['eventCode']
			notification.live = (request.POST['live'] == 'true')
			notification.success = (request.POST['success'] == 'true')
			notification.pspReference = request.POST['pspReference']
			notification.originalReference = request.POST['originalReference']
			notification.merchantReference = request.POST['merchantReference']
			notification.merchantAccountCode = request.POST['merchantAccountCode']
			notification.paymentMethod = request.POST['paymentMethod']
			notification.reason = request.POST['reason']
			try:
				notification.amount = int(request.POST['amount'] / 100) # We only deal in whole euros
			except:
				# Some notifications don't have amounts
				notification.amount = -1
			# Save this unconfirmed for now
			notification.save()


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
		elif notification.eventCode == 'AUTHORIZATION':
			process_authorization(notification)
		elif notification.eventCode == 'REPORT_AVAILABLE':
			process_new_report(notification)
		elif notification.eventCode in ('CAPTURE', ):
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

	# Return that we've consumed the report outside the transaction, in
	# the unlikely event that the COMMIT is what failed
	return HttpResponse('[accepted]', content_type='text/plain')
