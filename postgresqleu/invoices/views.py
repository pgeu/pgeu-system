from django.core.paginator import Paginator, EmptyPage, InvalidPage
from django.shortcuts import render, get_object_or_404
from django.forms.models import inlineformset_factory
from django.forms import ModelMultipleChoiceField
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Count, Max
from django.contrib import messages
from django.conf import settings

import base64
import StringIO
from datetime import datetime, timedelta
from decimal import Decimal

from postgresqleu.util.decorators import user_passes_test_or_error
from models import Invoice, InvoiceRow, InvoiceHistory, InvoicePaymentMethod, VatRate
from models import InvoiceRefund
from forms import InvoiceForm, InvoiceRowForm, RefundForm
from util import InvoiceWrapper, InvoiceManager, InvoicePresentationWrapper


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def paid(request):
    return _homeview(request, Invoice.objects.filter(paidat__isnull=False, deleted=False, finalized=True), paid=True)


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def unpaid(request):
    return _homeview(request, Invoice.objects.filter(paidat=None, deleted=False, finalized=True), unpaid=True)


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def pending(request):
    return _homeview(request, Invoice.objects.filter(finalized=False, deleted=False), pending=True)


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def deleted(request):
    return _homeview(request, Invoice.objects.filter(deleted=True), deleted=True)


# Not a view, just a utility function, thus no separate permissions check
def _homeview(request, invoice_objects, unpaid=False, pending=False, deleted=False, paid=False, searchterm=None):
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

    if paginator.num_pages > 15:
        if page < paginator.num_pages - 15:
            firstpage = max(1, page - 7)
            lastpage = firstpage + 15
        else:
            lastpage = min(paginator.num_pages + 1, page + 8)
            firstpage = lastpage - 15
        page_range = range(firstpage, lastpage)
    else:
        page_range = paginator.page_range

    has_pending = Invoice.objects.filter(finalized=False).exists()
    has_unpaid = Invoice.objects.filter(finalized=True, paidat__isnull=False).exists()
    return render(request, 'invoices/home.html', {
        'invoices': invoices,
        'paid': paid,
        'unpaid': unpaid,
        'pending': pending,
        'deleted': deleted,
        'has_pending': has_pending,
        'has_unpaid': has_unpaid,
        'searchterm': searchterm,
        'page_range': page_range,
        'breadcrumbs': [('/invoiceadmin/', 'Invoices'), ],
    })


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def search(request):
    if 'term' in request.POST:
        term = request.POST['term']
    elif 'term' in request.GET:
        term = request.GET['term']
    else:
        term = ''

    if term.strip() == '':
        messages.error(request, "No search term specified")
        return HttpResponseRedirect('/invoiceadmin/')

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


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@transaction.atomic
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
        if request.POST['submit'] == 'Delete':
            # No need to validate before deleting. But we do a double check
            # that the invoice is really not finalized.
            if invoice.finalized:
                raise Exception("Cannot delete a finalized invoice!")
            invoiceid = invoice.id  # Need to save this away since we delete it
            invoice.delete()
            messages.info(request, "Invoice %s deleted." % invoiceid)
            return HttpResponseRedirect('/invoiceadmin/')

        # Disabled SELECTs are not included in the POST. Therefor, we must copy the
        # data over for those fields.
        postcopy = request.POST.copy()
        if not invoicenum == 'new':
            for fld in ('accounting_account', 'accounting_object', ):
                if fld not in postcopy:
                    postcopy[fld] = getattr(invoice, fld)

        form = InvoiceForm(data=postcopy, instance=invoice)
        if form.instance.finalized:
            formset = InvoiceRowInlineFormset(instance=invoice)
        else:
            formset = InvoiceRowInlineFormset(data=postcopy, instance=invoice)
            formset.forms[0].empty_permitted = False
        if form.is_valid():
            if formset.is_valid() or form.instance.finalized:
                if form.instance.finalized:
                    # When finalized, only a very limited set of fields can be
                    # edited. This doesn't include the invoice rows, so don't
                    # even bother to save the fieldset.
                    form.instance.save(update_fields=[fn for fn in form.available_in_finalized if not isinstance(form[fn].field, ModelMultipleChoiceField)])
                    for m in form.instance.allowedmethods.all():
                        if m not in form.cleaned_data['allowedmethods']:
                            form.instance.allowedmethods.remove(m)
                    for i in form.cleaned_data['allowedmethods']:
                        form.instance.allowedmethods.add(i)
                else:
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
        # GET request, but it might be for an existing invoice
        if invoice:
            form = InvoiceForm(instance=invoice)
        else:
            form = InvoiceForm(initial={
                'invoicedate': datetime.now(),
                'duedate': datetime.now() + timedelta(days=31)}
            )
        formset = InvoiceRowInlineFormset(instance=invoice)

    if invoice.processor:
        manager = InvoiceManager()
        processor = manager.get_invoice_processor(invoice)
        adminurl = processor.get_admin_url(invoice)
    else:
        adminurl = None
    return render(request, 'invoices/invoiceform.html', {
        'form': form,
        'formset': formset,
        'invoice': invoice,
        'adminurl': adminurl,
        'currency_symbol': settings.CURRENCY_SYMBOL,
        'vatrates': VatRate.objects.all(),
        'breadcrumbs': [('/invoiceadmin/', 'Invoices'), ],
    })


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def flaginvoice(request, invoicenum):
    transaction.set_autocommit(False)

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

    (r, i, p) = mgr.process_incoming_payment(invoice.invoicestr,
                                             invoice.total_amount,
                                             request.POST['reason'],
                                             0,  # We assume this was a bank payment without cost
                                             settings.ACCOUNTING_MANUAL_INCOME_ACCOUNT,
                                             0,  # costaccount
                                             logger=payment_logger)

    if r != InvoiceManager.RESULT_OK:
        transaction.rollback()
        return HttpResponse("Failed to process payment flagging:\n%s" % str.getvalue(),
                            content_type="text/plain")

    # The invoice manager will have flagged the invoice properly as well,
    # so we can just return the user right back
    transaction.commit()
    return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@transaction.atomic
def cancelinvoice(request, invoicenum):
    invoice = get_object_or_404(Invoice, pk=invoicenum)

    reason = request.POST['reason']
    if not reason:
        return HttpResponseForbidden("Can't cancel an invoice without a reason!")

    manager = InvoiceManager()
    try:
        manager.cancel_invoice(invoice, reason)
    except Exception as ex:
        messages.warning(request, "Failed to cancel: %s" % ex)

    return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@transaction.atomic
def extend_cancel(request, invoicenum):
    invoice = get_object_or_404(Invoice, pk=invoicenum)

    try:
        days = int(request.GET.get('days', 5))
    except:
        days = 5

    invoice.canceltime += timedelta(days=days)
    invoice.save()

    InvoiceHistory(invoice=invoice, txt='Extended autocancel by {0} days to {1}'.format(days, invoice.canceltime)).save()

    return HttpResponseRedirect("/invoiceadmin/%s/" % invoice.id)


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@transaction.atomic
def refundinvoice(request, invoicenum):
    invoice = get_object_or_404(Invoice, pk=invoicenum)

    if request.method == 'POST':
        form = RefundForm(data=request.POST, invoice=invoice)
        if form.is_valid():
            # Do some sanity checking
            if form.cleaned_data['vatrate']:
                vatamount = (Decimal(form.cleaned_data['amount']) * form.cleaned_data['vatrate'].vatpercent / Decimal(100)).quantize(Decimal('0.01'))
                if vatamount > invoice.total_refunds['remaining']['vatamount']:
                    messages.error(request, "Unable to refund, VAT amount mismatch!")
                    return HttpResponseRedirect('.')
            else:
                vatamount = 0

            mgr = InvoiceManager()
            r = mgr.refund_invoice(invoice,
                                   form.cleaned_data['reason'],
                                   Decimal(form.cleaned_data['amount']),
                                   vatamount,
                                   form.cleaned_data['vatrate'],
            )
            if invoice.can_autorefund:
                messages.info(request, "Refund initiated.")
            else:
                messages.info(request, "Refund flagged.")

            return HttpResponseRedirect(".")
    else:
        form = RefundForm(invoice=invoice)

    # Check if all invoicerows have the same VAT rate (NULL or specified)
    vinfo = invoice.invoicerow_set.all().aggregate(n=Count('vatrate', distinct=True), v=Max('vatrate'))

    return render(request, 'invoices/refundform.html', {
        'form': form,
        'invoice': invoice,
        'breadcrumbs': [('/invoiceadmin/', 'Invoices'), ('/invoiceadmin/{0}/'.format(invoice.pk), 'Invoice #{0}'.format(invoice.pk)), ],
        })


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def previewinvoice(request, invoicenum):
    invoice = get_object_or_404(Invoice, pk=invoicenum)

    # We assume there is no PDF yet
    wrapper = InvoiceWrapper(invoice)
    r = HttpResponse(content_type='application/pdf')
    r.write(wrapper.render_pdf_invoice(True))
    return r


@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@transaction.atomic
def emailinvoice(request, invoicenum):
    if request.GET.get('really', None) != 'yes':
        return HttpResponse('Secret key is missing!', status=401)

    if 'reason' not in request.GET:
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

# --------------------------------------------------------------------------
#
# Views that are viewable both by admins and end users
# (if they have permissions)
#
# --------------------------------------------------------------------------


@login_required
def viewinvoice(request, invoiceid):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
    if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
        return HttpResponseForbidden("Access denied")

    return render(request, 'invoices/userinvoice.html', {
        'invoice': InvoicePresentationWrapper(invoice, "%s/invoices/%s/" % (settings.SITEBASE, invoice.pk)),
    })


def viewinvoice_secret(request, invoiceid, invoicesecret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=invoicesecret)
    return render(request, 'invoices/userinvoice.html', {
        'invoice': InvoicePresentationWrapper(invoice, "%s/invoices/%s/%s/" % (settings.SITEBASE, invoice.pk, invoice.recipient_secret)),
        'fromsecret': True,
    })


@login_required
def viewinvoicepdf(request, invoiceid):
    invoice = get_object_or_404(Invoice, pk=invoiceid)
    if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
        return HttpResponseForbidden("Access denied")

    r = HttpResponse(content_type='application/pdf')
    r.write(base64.b64decode(invoice.pdf_invoice))
    return r


def viewinvoicepdf_secret(request, invoiceid, invoicesecret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, recipient_secret=invoicesecret)
    r = HttpResponse(content_type='application/pdf')
    r.write(base64.b64decode(invoice.pdf_invoice))
    return r


@login_required
def viewreceipt(request, invoiceid):
    invoice = get_object_or_404(Invoice, pk=invoiceid)
    if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
        return HttpResponseForbidden("Access denied")

    r = HttpResponse(content_type='application/pdf')
    r.write(base64.b64decode(invoice.pdf_receipt))
    return r


def viewreceipt_secret(request, invoiceid, invoicesecret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, recipient_secret=invoicesecret)
    r = HttpResponse(content_type='application/pdf')
    r.write(base64.b64decode(invoice.pdf_receipt))
    return r


@login_required
def viewrefundnote(request, invoiceid, refundid):
    invoice = get_object_or_404(Invoice, pk=invoiceid)
    if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
        return HttpResponseForbidden("Access denied")
    refund = get_object_or_404(InvoiceRefund, invoice=invoiceid, pk=refundid)

    r = HttpResponse(content_type='application/pdf')
    r.write(base64.b64decode(refund.refund_pdf))
    return r


def viewrefundnote_secret(request, invoiceid, invoicesecret, refundid):
    invoice = get_object_or_404(Invoice, pk=invoiceid, recipient_secret=invoicesecret)
    refund = get_object_or_404(InvoiceRefund, invoice=invoice, pk=refundid)
    r = HttpResponse(content_type='application/pdf')
    r.write(base64.b64decode(refund.refund_pdf))
    return r


@login_required
def userhome(request):
    invoices = Invoice.objects.filter(recipient_user=request.user, deleted=False, finalized=True)
    return render(request, 'invoices/userhome.html', {
        'invoices': invoices,
    })


@login_required
def banktransfer(request):
    param = {
        'title': request.GET['title'],
        'amount': request.GET['amount'],
    }
    if 'ret' in request.GET:
        param['returnurl'] = request.GET['ret']

    return render(request, 'invoices/banktransfer.html', param)


@login_required
@transaction.atomic
def dummy_payment(request, invoiceid, invoicesecret):
    if not settings.DEBUG:
        return HttpResponse("Dummy payments not enabled")

    invoice = get_object_or_404(Invoice, pk=invoiceid, recipient_secret=invoicesecret)
    manager = InvoiceManager()
    if invoice.processor:
        processor = manager.get_invoice_processor(invoice)
        returnurl = processor.get_return_url(invoice)
    else:
        returnurl = "%s/invoices/%s/" % (settings.SITEBASE, invoice.pk)

    # We'll just cheat and use the Adyen account
    manager.process_incoming_payment_for_invoice(invoice, invoice.total_amount, 'Dummy payment', 0, settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, 0, None, None, InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.dummy.DummyPayment'))

    return HttpResponseRedirect(returnurl)
