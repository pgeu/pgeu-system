from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.utils.html import escape
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.db import transaction
from django.conf import settings

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.payment import payment_implementations
from postgresqleu.accounting.util import create_accounting_entry, get_account_choices
from postgresqleu.invoices.util import InvoiceManager

from postgresqleu.accounting.models import Account
from postgresqleu.invoices.models import InvoicePaymentMethod, Invoice, InvoiceLog
from postgresqleu.invoices.models import PendingBankTransaction
from postgresqleu.invoices.models import PendingBankMatcher
from postgresqleu.invoices.models import BankTransferFees
from postgresqleu.invoices.backendforms import BackendVatRateForm
from postgresqleu.invoices.backendforms import BackendVatValidationCacheForm
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm

from datetime import date
import re


def edit_vatrate(request, rest):
    authenticate_backend_group(request, 'Invoice managers')

    return backend_list_editor(request,
                               None,
                               BackendVatRateForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Invoices',
                               return_url='/admin/',
    )


def edit_vatvalidationcache(request, rest):
    authenticate_backend_group(request, 'Invoice managers')

    return backend_list_editor(request,
                               None,
                               BackendVatValidationCacheForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Invoices',
                               return_url='/admin/',
    )


@transaction.atomic
def banktransactions(request):
    authenticate_backend_group(request, 'Invoice managers')

    if request.method == 'POST':
        if 'submit' not in request.POST:
            return HttpResponseRedirect(".")

        if 'transid' in request.POST:
            trans = get_object_or_404(PendingBankTransaction, id=request.POST['transid'])

            if request.POST['submit'] == 'Discard':
                InvoiceLog(message="Discarded bank transaction of {0}{1} with text {2}".format(trans.amount, settings.CURRENCY_ABBREV, trans.transtext)).save()

                trans.delete()

                messages.info(request, "Transaction discarded")
                return HttpResponseRedirect(".")
            elif request.POST['submit'] == 'Create accounting record':
                pm = trans.method.get_implementation()

                accrows = [
                    (pm.config('bankaccount'), trans.transtext, trans.amount, None),
                ]
                entry = create_accounting_entry(date.today(), accrows, True)

                InvoiceLog(message="Created manual accounting entry for transaction of {0}{1} with text {2}".format(trans.amount, settings.CURRENCY_ABBREV, trans.transtext)).save()

                trans.delete()

                return HttpResponseRedirect("/accounting/e/{0}/".format(entry.id))
            else:
                raise Http404("Invalid request")
        elif 'matcherid' in request.POST:
            matcher = get_object_or_404(PendingBankMatcher, pk=request.POST['matcherid'])
            if request.POST['submit'] == 'Discard':
                InvoiceLog(message="Discarded pending bank matcher {0} for {1} {2}".format(matcher.pattern, matcher.amount, settings.CURRENCY_ABBREV)).save()

                matcher.delete()

                messages.info(request, "Matcher discarded")
                return HttpResponseRedirect(".")
            else:
                raise Http404("Invalid request")
        else:
            raise Http404("Invalid request")

    pendingtransactions = PendingBankTransaction.objects.order_by('created')
    pendingmatchers = PendingBankMatcher.objects.order_by('created')

    return render(request, 'invoices/banktransactions.html', {
        'transactions': pendingtransactions,
        'matchers': pendingmatchers,
        'topadmin': 'Invoices',
        'helplink': 'payment',
    })


def banktransactions_match(request, transid):
    authenticate_backend_group(request, 'Invoice managers')

    trans = get_object_or_404(PendingBankTransaction, pk=transid)
    invoices = Invoice.objects.filter(finalized=True, paidat__isnull=True, deleted=False).order_by('invoicedate')

    def _match_invoice(i):
        if i.total_amount == trans.amount:
            matchinfo = 'Amount matches exact'
            matchlabel = 'success'
        elif i.payment_reference in trans.transtext:
            matchinfo = 'Payment reference found'
            matchlabel = 'success'
        else:
            matchinfo = ''
            matchlabel = ''

        return {
            'matchinfo': matchinfo,
            'matchlabel': matchlabel,
            'i': i,
        }

    im = map(_match_invoice, invoices)

    pm = trans.method.get_implementation()
    matchers = PendingBankMatcher.objects.filter(foraccount__num=pm.config('bankaccount'), amount=trans.amount)

    return render(request, 'invoices/banktransactions_match.html', {
        'transaction': trans,
        'invoice_matchinfo': im,
        'matchers': matchers,
        'topadmin': 'Invoices',
        'breadcrumbs': [('/admin/invoices/banktransactions/', 'Pending bank transactions'), ],
        'helplink': 'payment',
    })


def banktransactions_match_invoice(request, transid, invoiceid):
    authenticate_backend_group(request, 'Invoice managers')

    trans = get_object_or_404(PendingBankTransaction, pk=transid)
    invoice = get_object_or_404(Invoice, pk=invoiceid)

    pm = trans.method.get_implementation()

    if request.method == 'POST':
        if pm.config('feeaccount'):
            fee_account = Account.objects.get(num=pm.config('feeaccount'))
        else:
            fee_account = get_object_or_404(Account, num=request.POST['account'])

        manager = InvoiceManager()
        invoicelog = []

        def invoicelogger(msg):
            invoicelog.append(msg)

        transaction.set_autocommit(False)
        (status, _invoice, _processor) = manager.process_incoming_payment_for_invoice(
            invoice,
            invoice.total_amount,
            "Bank transfer from {0} with id {1}, manually matched".format(trans.method.internaldescription, trans.methodidentifier),
            invoice.total_amount - trans.amount,  # Calculated fee
            pm.config('bankaccount'),
            fee_account.num,
            [],
            invoicelogger,
            trans.method)

        if status != manager.RESULT_OK:
            messages.error(request, "Failed to run invoice processor:")
            for m in invoicelog:
                messages.warning(request, m)

            # Roll back any changes so far
            transaction.rollback()

            return HttpResponseRedirect(".")

        BankTransferFees(invoice=invoice, fee=invoice.total_amount - trans.amount).save()

        InvoiceLog(message="Manually matched invoice {0} for {1} {2}, bank transaction {3} {2}, fees {4}".format(
            invoice.id,
            invoice.total_amount,
            settings.CURRENCY_ABBREV,
            trans.amount,
            invoice.total_amount - trans.amount,
        )).save()

        # Remove the pending transaction
        trans.delete()

        transaction.commit()
        return HttpResponseRedirect("/admin/invoices/banktransactions/")

    if pm.config('feeaccount'):
        fee_account = Account.objects.get(num=pm.config('feeaccount'))
        accounts = []
    else:
        fee_account = None
        accounts = get_account_choices()

    return render(request, 'invoices/banktransactions_match_invoice.html', {
        'transaction': trans,
        'invoice': invoice,
        'topadmin': 'Invoices',
        'fee_account': fee_account,
        'accounts': accounts,
        'match': {
            'amountdiff': invoice.total_amount - trans.amount,
            'absdiff': abs(invoice.total_amount - trans.amount),
            'percentdiff': (abs(invoice.total_amount - trans.amount) / invoice.total_amount) * 100,
            'found_ref': invoice.payment_reference in trans.transtext,
            'found_id': str(invoice.id) in trans.transtext,
            'highlight_ref': re.sub('({0})'.format(invoice.payment_reference), r'<strong>\1</strong>', escape(trans.transtext)),
            'highlight_id': re.sub('({0})'.format(invoice.id), r'<strong>\1</strong>', escape(trans.transtext)),
        },
        'breadcrumbs': [
            ('/admin/invoices/banktransactions/', 'Pending bank transactions'),
            ('/admin/invoices/banktransactions/{0}/'.format(trans.id), 'Transaction'),
        ],
        'helplink': 'payment',
    })


@transaction.atomic
def banktransactions_match_matcher(request, transid, matcherid):
    authenticate_backend_group(request, 'Invoice managers')

    trans = get_object_or_404(PendingBankTransaction, pk=transid)
    matcher = get_object_or_404(PendingBankMatcher, pk=matcherid)

    pm = trans.method.get_implementation()

    if request.method == 'POST':
        if trans.amount != matcher.amount:
            # Should not happen, but let's make sure
            messages.error(request, "Amount mismatch")
            return HttpResponseRedirect(".")

        if matcher.journalentry.closed:
            messages.error(request, "Accounting entry already closed")
            return HttpResponseRedirect(".")

        # The whole point of what we do here is to ignore the text of the match,
        # so once the amount is correct, we just complete it.
        matcher.journalentry.closed = True
        matcher.journalentry.save()

        InvoiceLog(message="Manually matched bank transaction of {0}{1} with text {2} to journal entry {3}.".format(
            trans.amount,
            settings.CURRENCY_ABBREV,
            trans.transtext,
            matcher.journalentry,
        )).save()

        # Remove both the pending transaction *and* the pending matcher
        trans.delete()
        matcher.delete()
        return HttpResponseRedirect("../../")

    return render(request, 'invoices/banktransactions_match_matcher.html', {
        'transaction': trans,
        'matcher': matcher,
        'topadmin': 'Invoices',
        'breadcrumbs': [
            ('/admin/invoices/banktransactions/', 'Pending bank transactions'),
            ('/admin/invoices/banktransactions/{0}/'.format(trans.id), 'Transaction'),
        ],
        'helplink': 'payment',
    })


def _load_formclass(classname):
    pieces = classname.split('.')
    modname = '.'.join(pieces[:-1])
    classname = pieces[-1]
    mod = __import__(modname, fromlist=[classname, ])
    if hasattr(getattr(mod, classname), 'backend_form_class'):
        return getattr(mod, classname).backend_form_class
    else:
        return BackendInvoicePaymentMethodForm


def edit_paymentmethod(request, rest):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    u = rest and rest.rstrip('/') or rest

    formclass = BackendInvoicePaymentMethodForm
    if u and u != '' and u.isdigit():
        # Editing an existing one, so pick the correct subclass!
        pm = get_object_or_404(InvoicePaymentMethod, pk=u)
        formclass = _load_formclass(pm.classname)
    elif u == 'new':
        if '_newformdata' in request.POST or 'paymentclass' in request.POST:
            if '_newformdata' in request.POST:
                c = request.POST['_newformdata']
            else:
                c = request.POST['paymentclass']

            if c not in payment_implementations:
                raise PermissionDenied()

            formclass = _load_formclass(c)

    return backend_list_editor(request,
                               None,
                               formclass,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Invoices',
                               return_url='/admin/',
    )
