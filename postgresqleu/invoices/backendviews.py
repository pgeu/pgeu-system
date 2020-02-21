from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, Http404
from django.utils.html import escape
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.db.models import Max, Q
from django.db import transaction
from django.conf import settings

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.payment import payment_implementations
from postgresqleu.util.pagination import simple_pagination
from postgresqleu.util.request import get_int_or_error
from postgresqleu.accounting.util import create_accounting_entry, get_account_choices
from postgresqleu.invoices.util import InvoiceManager

from postgresqleu.accounting.models import Account
from postgresqleu.invoices.models import InvoicePaymentMethod, Invoice, InvoiceLog
from postgresqleu.invoices.models import PendingBankTransaction
from postgresqleu.invoices.models import PendingBankMatcher
from postgresqleu.invoices.models import BankTransferFees
from postgresqleu.invoices.models import BankFileUpload, BankStatementRow
from postgresqleu.invoices.backendforms import BackendVatRateForm
from postgresqleu.invoices.backendforms import BackendVatValidationCacheForm
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm
from postgresqleu.invoices.backendforms import BankfilePaymentMethodChoiceForm
from postgresqleu.invoices.util import register_bank_transaction

from datetime import date
import re
import base64
from io import BytesIO


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
            trans = get_object_or_404(PendingBankTransaction, id=get_int_or_error(request.POST, 'transid'))

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
            elif request.POST['submit'] == 'Return to sender':
                pm = trans.method.get_implementation()

                pm.return_payment(trans)

                InvoiceLog(message="Scheduled transaction '{0}' ({1}{2}) for return to sender using {3}".format(trans.transtext, trans.amount, settings.CURRENCY_ABBREV, trans.method.internaldescription)).save()
                trans.delete()

                return HttpResponseRedirect(".")
            else:
                raise Http404("Invalid request")
        elif 'matcherid' in request.POST:
            matcher = get_object_or_404(PendingBankMatcher, pk=get_int_or_error(request.POST, 'matcherid'))
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
        matchinfos = []
        if i.total_amount == trans.amount:
            matchinfos.append('Amount matches exact')
        if i.payment_reference in trans.transtext.replace(' ', ''):
            matchinfos.append('Payment reference found')

        return {
            'matchinfo': ",\n".join(matchinfos),
            'matchlabel': len(matchinfos) > 0 and 'success' or '',
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


def bankfiles(request):
    authenticate_backend_group(request, 'Invoice managers')

    if request.method == 'POST':
        # Uploading a file!
        method = get_object_or_404(InvoicePaymentMethod, active=True, config__has_key='file_upload_interval', id=get_int_or_error(request.POST, 'id'))

        impl = method.get_implementation()
        # Stage 1 upload has the file in request.FILES. Stage 2 has it in a hidden field in the form instead,
        # because we can't make it upload th file twice.
        if 'fc' in request.POST:
            # In stage 2 the file is included ase base64
            txt = impl.convert_uploaded_file_to_utf8(BytesIO(base64.b64decode(request.POST['fc'])))

            try:
                rows = impl.parse_uploaded_file_to_rows(txt)
                (anyerror, extrakeys, hasvaluefor) = impl.process_loaded_rows(rows)

                numrows = len(rows)
                numtrans = 0
                numpending = 0
                numerrors = 0

                with transaction.atomic():
                    # Store thef file itself
                    bankfile = BankFileUpload(method=method,
                                              parsedrows=numrows,
                                              newtrans=0,
                                              newpending=0,
                                              errors=0,
                                              uploadby=request.user.username,
                                              name=request.POST['name'],
                                              textcontents=txt,
                    )
                    bankfile.save()  # To get an id we can use

                    for r in rows:
                        if r['row_already_exists']:
                            continue
                        if r.get('row_errors', []):
                            numerrors += 1
                            continue

                        # Insert the row
                        b = BankStatementRow(method=method,
                                             fromfile=bankfile,
                                             uniqueid=r.get('uniqueid', None),
                                             date=r['date'],
                                             amount=r['amount'],
                                             description=r['text'],
                                             balance=r.get('balance', None),
                                             other=r['other'],
                        )
                        b.save()
                        numtrans += 1

                        if not register_bank_transaction(b.method, b.id, b.amount, b.description, ''):
                            # This means the transaction wasn't directly matched and has been
                            # registered as a pending transaction.
                            numpending += 1

                    bankfile.newtrans = numtrans
                    bankfile.newpending = numpending
                    bankfile.errors = numerrors
                    bankfile.save()
            except Exception as e:
                messages.error(request, "Error uploading file: {}".format(e))

            return HttpResponseRedirect(".")

        if 'f' not in request.FILES:
            messages.error(request, "No file included in upload")
        elif request.FILES['f'].size < 1:
            messages.error(request, "Uploaded file is empty")
        else:
            f = request.FILES['f']

            try:
                # Stage 1, mean we parse it and render a second form to confirm
                rows = impl.parse_uploaded_file_to_rows(impl.convert_uploaded_file_to_utf8(f))
                (anyerror, extrakeys, hasvaluefor) = impl.process_loaded_rows(rows)

                f.seek(0)

                return render(request, 'invoices/bankfile_uploaded.html', {
                    'method': method,
                    'rows': rows,
                    'extrakeys': sorted(extrakeys),
                    'hasvaluefor': hasvaluefor,
                    'anyerror': anyerror,
                    'filename': f.name,
                    'fc': base64.b64encode(f.read()),
                    'topadmin': 'Invoices',
                    'helplink': 'payment',
                    'breadcrumbs': [('../../', 'Bank files'), ],
                })
            except Exception as e:
                messages.error(request, "Error uploading file: {}".format(e))

    methods = InvoicePaymentMethod.objects.filter(active=True, config__has_key='file_upload_interval').annotate(latest_file=Max('bankfileupload__created'))
    file_objects = BankFileUpload.objects.select_related('method').all().order_by('-created')[:1000]
    (files, paginator, page_range) = simple_pagination(request, file_objects, 50)

    return render(request, 'invoices/bankfiles.html', {
        'files': files,
        'page_range': page_range,
        'methods': methods,
        'topadmin': 'Invoices',
        'helplink': 'payment',
    })


def bankfile_transaction_methodchoice(request):
    authenticate_backend_group(request, 'Invoice managers')

    methods = InvoicePaymentMethod.objects.filter(config__has_key='file_upload_interval').order_by('internaldescription')
    if not methods:
        # Should never happen since the button is only visible if they exist
        messages.error(request, "No managed bank providers configured!")
        return HttpResponseRedirect("/admin/")

    if len(methods) == 1:
        # Only one, so no need for prompt
        return HttpResponseRedirect("{}/".format(methods[0].id))

    if request.method == 'POST':
        form = BankfilePaymentMethodChoiceForm(methods=methods, data=request.POST)
        if form.is_valid():
            return HttpResponseRedirect("{}/".format(form.cleaned_data['paymentmethod'].id))
    else:
        form = BankfilePaymentMethodChoiceForm(methods=methods)

    return render(request, 'confreg/admin_backend_form.html', {
        'basetemplate': 'adm/admin_base.html',
        'form': form,
        'whatverb': 'View',
        'what': 'bank transactions',
        'savebutton': 'View transactions',
        'cancelurl': '/admin/',
        'cancelname': 'Back',
        'topadmin': 'Invoices',
        'helplink': 'payment',
    })


def bankfile_transactions(request, methodid):
    authenticate_backend_group(request, 'Invoice managers')

    method = get_object_or_404(InvoicePaymentMethod, pk=methodid)

    # Needed for backlinks
    methodcount = InvoicePaymentMethod.objects.filter(config__has_key='file_upload_interval').count()

    backbutton = "../"
    breadlabel = "Bank transactions"

    if methodcount == 1:
        # If there is only one method, we have to return all the way back to the index page, or we'll
        # just get redirected back to ourselves.
        backbutton = "/admin/"

    q = Q(method=method)
    if 'file' in request.GET:
        q = q & Q(fromfile=get_int_or_error(request.GET, 'file'))
        backbutton = "../../"
        breadlabel = "Bankfiles"

    allrows = BankStatementRow.objects.filter(q).order_by('-date', 'id')
    (rows, paginator, page_range) = simple_pagination(request, allrows, 50)

    extrakeys = set()
    hasvaluefor = {
        'uniqueid': False,
        'balance': False,
    }
    for r in rows:
        extrakeys.update(r.other.keys())
        for k in hasvaluefor.keys():
            if getattr(r, k, None):
                hasvaluefor[k] = True

    params = request.GET.copy()
    if 'page' in params:
        del params['page']

    return render(request, 'invoices/bankfile_transactions.html', {
        'rows': rows,
        'extrakeys': extrakeys,
        'hasvaluefor': hasvaluefor,
        'page_range': page_range,
        'topadmin': 'Invoices',
        'helplink': 'payment',
        'requestparams': params.urlencode(),
        'breadcrumbs': [(backbutton, breadlabel), ],
        'backbutton': backbutton,
    })


def _flag_invoices(request, trans, invoices, pm, fee_account):
    manager = InvoiceManager()
    invoicelog = []

    transaction.set_autocommit(False)

    def invoicelogger(msg):
        invoicelog.append(msg)

    if len(invoices) == 1:
        fee = invoices[0].total_amount - trans.amount  # Calculated fee
    else:
        # There can be no fees when using multiple invoices, so ensure that
        if sum([i.total_amount for i in invoices]) != trans.amount:
            raise Exception("Fees not supported for multi-invoice flagging")
        fee = 0

    for invoice in invoices:
        (status, _invoice, _processor) = manager.process_incoming_payment_for_invoice(
            invoice,
            invoice.total_amount,
            "Bank transfer from {0} with id {1}, manually matched".format(trans.method.internaldescription, trans.methodidentifier),
            fee,
            pm.config('bankaccount'),
            fee_account and fee_account.num,
            [],
            invoicelogger,
            trans.method)

        if status != manager.RESULT_OK:
            messages.error(request, "Failed to run invoice processor:")
            for m in invoicelog:
                messages.warning(request, m)

            # Roll back any changes so far
            transaction.rollback()

            return False

        BankTransferFees(invoice=invoice, fee=fee).save()

        InvoiceLog(message="Manually matched invoice {0} for {1} {2}, bank transaction {3} {2}, fees {4}".format(
            invoice.id,
            invoice.total_amount,
            settings.CURRENCY_ABBREV,
            trans.amount,
            fee,
        )).save()

    # Remove the pending transaction
    trans.delete()

    transaction.commit()

    return True


def banktransactions_match_invoice(request, transid, invoiceid):
    authenticate_backend_group(request, 'Invoice managers')

    trans = get_object_or_404(PendingBankTransaction, pk=transid)
    invoice = get_object_or_404(Invoice, pk=invoiceid)

    pm = trans.method.get_implementation()

    if request.method == 'POST':
        if pm.config('feeaccount'):
            fee_account = Account.objects.get(num=pm.config('feeaccount'))
        else:
            fee_account = get_object_or_404(Account, num=get_int_or_error(request.POST, 'account'))

        r = _flag_invoices(request,
                           trans,
                           [invoice, ],
                           pm,
                           fee_account)

        if r:
            return HttpResponseRedirect("/admin/invoices/banktransactions/")
        else:
            return HttpResponseRedirect(".")

    # Generate the form

    if pm.config('feeaccount'):
        fee_account = Account.objects.get(num=pm.config('feeaccount'))
        accounts = []
    else:
        fee_account = None
        accounts = get_account_choices()

    return render(request, 'invoices/banktransactions_match_invoice.html', {
        'transaction': trans,
        'invoices': [invoice, ],
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


def banktransactions_match_multiple(request, transid):
    authenticate_backend_group(request, 'Invoice managers')

    trans = get_object_or_404(PendingBankTransaction, pk=transid)

    pm = trans.method.get_implementation()

    invoices = [get_object_or_404(Invoice, pk=invoiceid) for invoiceid in request.GET.getlist('invoiceid')]
    if not invoices:
        invoices = [get_object_or_404(Invoice, pk=invoiceid) for invoiceid in request.POST.get('invoiceidlist').split(',')]

    if len(invoices) == 0:
        raise Http404("No invoices")

    if request.method == 'POST':
        r = _flag_invoices(request, trans, invoices, pm, None)
        if r:
            return HttpResponseRedirect("/admin/invoices/banktransactions/")
        else:
            return HttpResponseRedirect(".")

    total_amount = sum([i.total_amount for i in invoices])

    return render(request, 'invoices/banktransactions_match_invoice.html', {
        'transaction': trans,
        'invoices': invoices,
        'topadmin': 'Invoices',
        'match': {
            'amountdiff': total_amount - trans.amount,
            'absdiff': abs(total_amount - trans.amount),
            'percentdiff': (abs(total_amount - trans.amount) / total_amount) * 100,
        },
        'cantmatch': (total_amount != trans.amount),
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
