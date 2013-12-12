from django.core.paginator import Paginator
from django.shortcuts import render_to_response, get_object_or_404
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db.transaction import commit_on_success
from django.db.models import Q
from django.template import RequestContext
from django.contrib import messages
from django.conf import settings

import base64
import StringIO

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required
from models import *
from forms import InvoiceForm, InvoiceRowForm
from util import InvoiceWrapper, InvoiceManager, InvoicePresentationWrapper

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def home(request):
	return _homeview(request, Invoice.objects.all())

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def unpaid(request):
	return _homeview(request, Invoice.objects.filter(paidat=None, deleted=False, finalized=True), unpaid=True)

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def pending(request):
	return _homeview(request, Invoice.objects.filter(finalized=False, deleted=False), pending=True)

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def deleted(request):
	return _homeview(request, Invoice.objects.filter(deleted=True), deleted=True)

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def refunded(request):
	return _homeview(request, Invoice.objects.filter(refunded=True), refunded=True)

# Not a view, just a utility function, thus no separate permissions check
def _homeview(request, invoice_objects, unpaid=False, pending=False, deleted=False, refunded=False, searchterm=None):
	# Render a list of all invoices
	paginator = Paginator(invoice_objects, 5)

	try:
		page = int(request.GET.get("page", "1"))
	except ValueError:
		page = 1

	try:
		invoices = paginator.page(page)
	except (EmptyPage, InvalidPage):
		invoices = paginator.page(paginator.num_pages)

	return render_to_response('invoices/home.html', {
			'invoices': invoices,
			'unpaid': unpaid,
			'pending': pending,
			'deleted': deleted,
			'refunded': refunded,
			'searchterm': searchterm,
			}, context_instance=RequestContext(request))


@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def search(request):
	if request.POST.has_key('term'):
		term = request.POST['term']
	elif request.GET.has_key('term'):
		term = request.GET['term']
	else:
		raise Exception("Sorry, need a search term!")

	try:
		invoiceid = int(term)
		try:
			invoice = Invoice.objects.get(pk=invoiceid)
			return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)
		except Invoice.DoesNotExist:
			messages.warning(request, "No invoice with id %s found." % invoiceid)
			return HttpResponseRedirect("/invoiceadmin/")
	except ValueError:
		# Not an integer, so perform an actual search...
		pass

	invoices = list(Invoice.objects.filter(Q(recipient_name__icontains=term) | Q(recipient_address__icontains=term) | Q(title__icontains=term)))
	if len(invoices) == 0:
		messages.warning(request, "No invoice matching '%s' found." % term)
		return HttpResponseRedirect("/invoiceadmin/")
	if len(invoices) == 1:
		return HttpResponseRedirect("/invoiceadmin/%s/" % invoices[0].id)

	messages.info(request, "Showing %s search hits for %s" % (len(invoices), term))
	return _homeview(request, invoices, searchterm=term)

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@commit_on_success
def oneinvoice(request, invoicenum):
	# Called to view an invoice, to edit one, and to create a new one,
	# since they're all based on the same model and form.
	if invoicenum == 'new':
		invoice = Invoice()
	else:
		invoice = get_object_or_404(Invoice, pk=invoicenum)

	def rowfield_callback(field, **kwargs):
		f = field.formfield()
		if invoice.finalized and f:
			if type(f.widget).__name__ == 'TextInput':
				f.widget.attrs['readonly'] = "readonly"
			else:
				f.widget.attrs['disabled'] = True
		return f

	can_delete = not invoice.finalized
	InvoiceRowInlineFormset = inlineformset_factory(Invoice, InvoiceRow, InvoiceRowForm, can_delete=can_delete, formfield_callback=rowfield_callback)

	if request.method == 'POST':
		form = InvoiceForm(data=request.POST, instance=invoice)
		formset = InvoiceRowInlineFormset(data=request.POST, instance=invoice)
		formset.forms[0].empty_permitted = False
		if form.is_valid():
			if formset.is_valid():
				# Need to set totalamount to something here, so it doesn't
				# cause an exception. It'll get fixed when we finalize!
				if not form.instance.finalized:
					form.instance.total_amount = -1
				form.save()
				formset.save()

				if request.POST['submit'] == 'Finalize':
					# Finalize this invoice. It's already been saved..
					wrapper = InvoiceWrapper(form.instance)
					wrapper.finalizeInvoice()
				elif request.POST['submit'] == 'Preview':
					return HttpResponseRedirect("/invoiceadmin/%s/preview/" % form.instance.pk)

				return HttpResponseRedirect("/invoiceadmin/%s/" % form.instance.pk)
		# Else fall through
	else:
		form = InvoiceForm(instance=invoice)
		formset = InvoiceRowInlineFormset(instance=invoice)

	return render_to_response('invoices/invoiceform.html', {
			'form': form,
			'formset': formset,
			'invoice': invoice,
			}, context_instance=RequestContext(request))

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@commit_on_success
def flaginvoice(request, invoicenum):
	invoice = get_object_or_404(Invoice, pk=invoicenum)

	reason = request.POST['reason']
	if not reason:
		return HttpResponseForbidden("Can't flag an invoice without a reason!")

	# Manually flag an invoice. What we do is call the invoice manager
	# with a fake transaction info. The invoice manager will know to call
	# whatever submodule generated the invoice.
	mgr = InvoiceManager()
	str = StringIO.StringIO()
	def payment_logger(msg):
		str.write(msg)
	(r,i,p) = mgr.process_incoming_payment(invoice.invoicestr,
										   invoice.total_amount,
										   request.POST['reason'],
										   0, # We assume this was a bank payment without cost
										   settings.ACCOUNTING_MANUAL_INCOME_ACCOUNT,
										   0, # costaccount
										   payment_logger)

	if r != InvoiceManager.RESULT_OK:
		return HttpResponse("Failed to process payment flagging:\n%s" % str.getvalue()
							, content_type="text/plain")

	# The invoice manager will have flagged the invoice properly as well,
	# so we can just return the user right back
	return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@commit_on_success
def cancelinvoice(request, invoicenum):
	invoice = get_object_or_404(Invoice, pk=invoicenum)

	reason = request.POST['reason']
	if not reason:
		return HttpResponseForbidden("Can't cancel an invoice without a reason!")

	manager = InvoiceManager()
	manager.cancel_invoice(invoice, reason)

	return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)


@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@commit_on_success
def refundinvoice(request, invoicenum):
	invoice = get_object_or_404(Invoice, pk=invoicenum)

	reason = request.POST['reason']
	if not reason:
		return HttpResponseForbidden("Can't refund an invoice without a reason!")

	manager = InvoiceManager()
	manager.refund_invoice(invoice, reason)

	return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def previewinvoice(request, invoicenum):
	invoice = get_object_or_404(Invoice, pk=invoicenum)

	# We assume there is no PDF yet
	wrapper = InvoiceWrapper(invoice)
	r = HttpResponse(mimetype='application/pdf')
	r.write(wrapper.render_pdf_invoice(True))
	return r

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@commit_on_success
def emailinvoice(request, invoicenum):
	if not (request.GET.has_key('really') and request.GET['really'] == 'yes'):
		return HttpResponse('Secret key is missing!', status=401)

	if not request.GET.has_key('reason'):
		return HttpResponse('Reason is missing!', status=401)
	if not request.GET['reason'] in ('initial', 'reminder'):
		return HttpResponse('Invalid reason given!', status=401)

	invoice = get_object_or_404(Invoice, pk=invoicenum)

	if not invoice.finalized:
		return HttpResponse("Not finalized!", status=401)

	# Ok, it seems we're good to go...
	wrapper = InvoiceWrapper(invoice)
	if request.GET['reason'] == 'initial':
		wrapper.email_invoice()
	elif request.GET['reason'] == 'reminder':
		wrapper.email_reminder()
	else:
		raise Exception("Cannot happen")

	return HttpResponse("OK")

#--------------------------------------------------------------------------
#
# Views that are viewable both by admins and end users
# (if they have permissions)
#
#--------------------------------------------------------------------------


@ssl_required
@login_required
def viewinvoice(request, invoiceid):
	invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
	if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
		return HttpResponseForbidden("Access denied")

	return render_to_response('invoices/userinvoice.html', {
			'invoice': InvoicePresentationWrapper(invoice, "%s/invoices/%s/" % (settings.SITEBASE_SSL, invoice.pk)),
			})

@ssl_required
def viewinvoice_secret(request, invoiceid, invoicesecret):
	invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=invoicesecret)
	return render_to_response('invoices/userinvoice.html', {
			'invoice': InvoicePresentationWrapper(invoice, "%s/invoices/%s/%s/" % (settings.SITEBASE_SSL, invoice.pk, invoice.recipient_secret)),
			'fromsecret': True,
			})

@ssl_required
@login_required
def viewinvoicepdf(request, invoiceid):
	invoice = get_object_or_404(Invoice, pk=invoiceid)
	if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
		return HttpResponseForbidden("Access denied")

	r = HttpResponse(mimetype='application/pdf')
	r.write(base64.b64decode(invoice.pdf_invoice))
	return r

@ssl_required
def viewinvoicepdf_secret(request, invoiceid, invoicesecret):
	invoice = get_object_or_404(Invoice, pk=invoiceid, recipient_secret=invoicesecret)
	r = HttpResponse(mimetype='application/pdf')
	r.write(base64.b64decode(invoice.pdf_invoice))
	return r

@ssl_required
@login_required
def viewreceipt(request, invoiceid):
	invoice = get_object_or_404(Invoice, pk=invoiceid)
	if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
		return HttpResponseForbidden("Access denied")

	r = HttpResponse(mimetype='application/pdf')
	r.write(base64.b64decode(invoice.pdf_receipt))
	return r

@ssl_required
def viewreceipt_secret(request, invoiceid, invoicesecret):
	invoice = get_object_or_404(Invoice, pk=invoiceid, recipient_secret=invoicesecret)
	r = HttpResponse(mimetype='application/pdf')
	r.write(base64.b64decode(invoice.pdf_receipt))
	return r

@ssl_required
@login_required
def userhome(request):
	invoices = Invoice.objects.filter(recipient_user=request.user, deleted=False, finalized=True)
	return render_to_response('invoices/userhome.html', {
			'invoices': invoices,
			})

@ssl_required
@login_required
def banktransfer(request):
	return render_to_response('invoices/banktransfer.html', {
			'title': request.GET['title'],
			'amount': request.GET['amount'],
			'returnurl': request.GET['ret'],
			})
