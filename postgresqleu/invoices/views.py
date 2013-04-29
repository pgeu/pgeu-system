from django.core.paginator import Paginator
from django.shortcuts import render_to_response, get_object_or_404
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db.transaction import commit_on_success
from django.template import RequestContext
from django.conf import settings

import base64
import StringIO

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required
from models import *
from forms import InvoiceForm, InvoiceRowForm
from util import InvoiceWrapper, InvoiceManager, InvoicePresentationWrapper

@login_required
@ssl_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def home(request):
	return _homeview(request, Invoice.objects.all())

@login_required
@ssl_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def unpaid(request):
	return _homeview(request, Invoice.objects.filter(paidat=None, deleted=False, finalized=True), unpaid=True)

@login_required
@ssl_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def pending(request):
	return _homeview(request, Invoice.objects.filter(finalized=False, deleted=False), pending=True)

# Not a view, just a utility function, thus no separate permissions check
def _homeview(request, invoice_objects, unpaid=False, pending=False):
	# Render a list of all invoices
	paginator = Paginator(invoice_objects, 50)

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
			})


@login_required
@ssl_required
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

@login_required
@ssl_required
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
										   payment_logger)

	if r != InvoiceManager.RESULT_OK:
		return HttpResponse("Failed to process payment flagging:\n%s" % str.getvalue()
							, content_type="text/plain")

	# The invoice manager will have flagged the invoice properly as well,
	# so we can just return the user right back
	return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)


@login_required
@ssl_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def previewinvoice(request, invoicenum):
	invoice = get_object_or_404(Invoice, pk=invoicenum)

	# We assume there is no PDF yet
	wrapper = InvoiceWrapper(invoice)
	r = HttpResponse(mimetype='application/pdf')
	r.write(wrapper.render_pdf_invoice(True))
	return r



#--------------------------------------------------------------------------
#
# Views that are viewable both by admins and end users
# (if they have permissions)
#
#--------------------------------------------------------------------------


@login_required
@ssl_required
def viewinvoice(request, invoiceid):
	invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
	if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
		return HttpResponseForbidden("Access denied")

	return render_to_response('invoices/userinvoice.html', {
			'invoice': InvoicePresentationWrapper(invoice, "%s/invoices/%s/" % (settings.SITEBASE_SSL, invoice.pk)),
			})

@login_required
@ssl_required
def viewinvoicepdf(request, invoiceid):
	invoice = get_object_or_404(Invoice, pk=invoiceid)
	if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
		return HttpResponseForbidden("Access denied")

	r = HttpResponse(mimetype='application/pdf')
	r.write(base64.b64decode(invoice.pdf_invoice))
	return r

@login_required
@ssl_required
def viewreceipt(request, invoiceid):
	invoice = get_object_or_404(Invoice, pk=invoiceid)
	if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
		return HttpResponseForbidden("Access denied")

	r = HttpResponse(mimetype='application/pdf')
	r.write(base64.b64decode(invoice.pdf_receipt))
	return r

@login_required
@ssl_required
def userhome(request):
	invoices = Invoice.objects.filter(recipient_user=request.user, deleted=False, finalized=True)
	return render_to_response('invoices/userhome.html', {
			'invoices': invoices,
			})

@login_required
@ssl_required
def banktransfer(request):
	return render_to_response('invoices/banktransfer.html', {
			'title': request.GET['title'],
			'amount': request.GET['amount'],
			'returnurl': request.GET['ret'],
			})
