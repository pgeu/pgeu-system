from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.db import transaction
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings

import base64

from postgresqleu.util.decorators import ssl_required
from postgresqleu.util.payment.adyen import calculate_signature
from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceManager

from models import RawNotification, AdyenLog, ReturnAuthorizationStatus
from util import process_raw_adyen_notification

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
		# Sometimes Adyen sends notifications without authorization headers.
		# In this case, we request authrorization and they will try again
		r = HttpResponse('Unauthorized', status=401)
		r['WWW-Authenticate'] = 'Basic realm="postgresqleu adyen"'
		return r

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

	if process_raw_adyen_notification(raw, request.POST):
		return HttpResponse('[accepted]', content_type='text/plain')
	else:
		return HttpResponse('[internal error]', content_type='text/plain')

