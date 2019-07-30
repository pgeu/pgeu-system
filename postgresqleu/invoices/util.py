from django.db import transaction
from django.conf import settings

from collections import defaultdict
from datetime import datetime, date
from dateutil import rrule
from decimal import Decimal
import importlib
import os
import base64
import re
import io
from Crypto.Hash import SHA256
from Crypto import Random

from postgresqleu.mailqueue.util import send_template_mail, send_simple_mail
from postgresqleu.accounting.util import create_accounting_entry

from .models import Invoice, InvoiceRow, InvoiceHistory, InvoiceLog
from .models import InvoiceRefund
from .models import InvoicePaymentMethod, PaymentMethodWrapper
from .models import PendingBankTransaction, PendingBankMatcher
from postgresqleu.accounting.models import Account


# Proxy around an invoice that adds presentation information,
# such as the ability to render a return URL for the invoice.
# It also blocks access to unsafe variables that could be used
# to traverse the object tree outside the invoice.
class InvoicePresentationWrapper(object):
    class Meta:
        proxy = True

    _unsafe_attributes = ('recipient_user', 'processor', 'allowedmethods', 'paidusing', )

    def __init__(self, invoice, returnurl):
        self.__invoice = invoice
        self.__returnurl = returnurl

    def __getattr__(self, name):
        # Most attributes are perfectly safe to return, but there are a couple that needs "sandboxing"
        if name in self._unsafe_attributes:
            return None

        return getattr(self.__invoice, name)

    @property
    def allowedmethodwrappers(self):
        return [PaymentMethodWrapper(m, self.__invoice, self.__returnurl) for m in self.allowedmethods.filter(active=True)]


# Functionality wrapper around an invoice that allows actions
# to be performed on it, such as creating PDFs.
class InvoiceWrapper(object):
    def __init__(self, invoice):
        self.invoice = invoice

    def finalizeInvoice(self):
        # This will close out this invoice for editing, and also
        # generate the actual PDF

        # Calculate the total
        total = Decimal(0)
        totalvat = Decimal(0)
        for r in self.invoice.invoicerow_set.all():
            total += r.rowamount * r.rowcount
            totalvat += r.totalvat
        totalvat = totalvat.quantize(Decimal('.01'))  # Round off to two digits
        self.invoice.total_amount = total + totalvat
        self.invoice.total_vat = totalvat

        if self.invoice.reverse_vat and self.invoice.total_vat > 0:
            raise Exception("Can't have both reverse VAT and a non-zero VAT!")

        # Generate a secret key that can be used to view the invoice if
        # there is no associated account
        s = SHA256.new()
        r = Random.new()
        s.update(self.invoice.pdf_invoice.encode('ascii'))
        s.update(r.read(250))
        self.invoice.recipient_secret = s.hexdigest()

        # Generate pdf
        self.invoice.pdf_invoice = base64.b64encode(self.render_pdf_invoice())

        # Indicate that we're finalized
        self.invoice.finalized = True

        # And we're done!
        self.invoice.save()
        InvoiceHistory(invoice=self.invoice, txt='Finalized').save()

    def render_pdf_invoice(self, preview=False):
        return self._render_pdf(preview=preview, receipt=False)

    def render_pdf_receipt(self):
        return self._render_pdf(receipt=True)

    def _render_pdf(self, preview=False, receipt=False):
        (modname, classname) = settings.INVOICE_PDF_BUILDER.rsplit('.', 1)
        PDFInvoice = getattr(importlib.import_module(modname), classname)
        if self.invoice.recipient_secret:
            paymentlink = '{0}/invoices/{1}/{2}/'.format(settings.SITEBASE, self.invoice.pk, self.invoice.recipient_secret)
        else:
            paymentlink = None

        # Include bank info on the invoice if any payment method chosen
        # provides it. If more than one supports it then the one with
        # the highest priority (=lowest sortkey) will be used.
        for pm in self.invoice.allowedmethods.all():
            if pm.config and 'bankinfo' in pm.config and len(pm.config['bankinfo']) > 1:
                m = pm.get_implementation()
                if not (hasattr(m, 'available') and not m.available(self.invoice)):
                    bankinfo = pm.config['bankinfo']
                    break
        else:
            bankinfo = None

        pdfinvoice = PDFInvoice(self.invoice.title,
                                "%s\n%s" % (self.invoice.recipient_name, self.invoice.recipient_address),
                                self.invoice.invoicedate,
                                receipt and self.invoice.paidat or self.invoice.duedate,
                                self.invoice.pk,
                                preview=preview,
                                receipt=receipt,
                                bankinfo=bankinfo,
                                paymentref=self.invoice.payment_reference,
                                totalvat=self.invoice.total_vat,
                                reverse_vat=self.invoice.reverse_vat,
                                paymentlink=paymentlink,
                            )

        # Order of rows is important - so preserve whatever order they were created
        # in. This is also the order that they get rendered by automatically by
        # djangos inline forms, so it should be consistent with whatever is shown
        # on the website.
        for r in self.invoice.invoicerow_set.all().order_by('id'):
            pdfinvoice.addrow(r.rowtext, r.rowamount, r.rowcount, r.vatrate)

        return pdfinvoice.save().getvalue()

    def render_pdf_refund(self, refund):
        (modname, classname) = settings.REFUND_PDF_BUILDER.rsplit('.', 1)
        PDFRefund = getattr(importlib.import_module(modname), classname)
        pdfnote = PDFRefund("%s\n%s" % (self.invoice.recipient_name, self.invoice.recipient_address),
                            self.invoice.invoicedate,
                            refund.completed,
                            self.invoice.id,
                            self.invoice.total_amount - self.invoice.total_vat,
                            self.invoice.total_vat,
                            refund.amount,
                            refund.vatamount,
                            self.used_payment_details(),
                            refund.id,
                            refund.reason,
                            self.invoice.total_refunds['amount'] - refund.amount,
                            self.invoice.total_refunds['vatamount'] - refund.vatamount,
        )

        return pdfnote.save().getvalue()

    def used_payment_details(self):
        try:
            pm = PaymentMethodWrapper(self.invoice.paidusing, self.invoice)
            return pm.used_method_details
        except:
            raise

    def email_receipt(self):
        # If no receipt exists yet, we have to bail too
        if not self.invoice.pdf_receipt:
            return

        self._email_something('paid_receipt.txt',
                              'Receipt for %s #%s' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
                              '%s_receipt_%s.pdf' % (settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
                              self.invoice.pdf_receipt,
                              bcc=(self.invoice.processor is None))
        InvoiceHistory(invoice=self.invoice, txt='Sent receipt').save()

    def email_invoice(self):
        if not self.invoice.pdf_invoice:
            return

        self._email_something('invoice.txt',
                              '%s #%s' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
                              '%s_invoice_%s.pdf' % (settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
                              self.invoice.pdf_invoice,
                              bcc=True)
        InvoiceHistory(invoice=self.invoice, txt='Sent invoice to %s' % self.invoice.recipient_email).save()

    def email_reminder(self):
        if not self.invoice.pdf_invoice:
            return

        self._email_something('invoice_reminder.txt',
                              '%s #%s - reminder' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
                              '%s_invoice_%s.pdf' % (settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
                              self.invoice.pdf_invoice,
                              bcc=True)
        InvoiceHistory(invoice=self.invoice, txt='Sent reminder to %s' % self.invoice.recipient_email).save()

    def email_cancellation(self, reason):
        self._email_something('invoice_cancel.txt',
                              '%s #%s - canceled' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
                              bcc=True,
                              extracontext={'reason': reason},
        )
        InvoiceHistory(invoice=self.invoice, txt='Sent cancellation').save()

    def email_refund_initiated(self, refund):
        self._email_something('invoice_refund_initiated.txt',
                              '%s #%s - refund initiated' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
                              bcc=True,
                              extracontext={'refund': refund}
        )
        InvoiceHistory(invoice=self.invoice, txt='Sent refund initiated notice').save()

    def email_refund_sent(self, refund):
        # Generate the refund notice so we have something to send
        refund.refund_pdf = base64.b64encode(self.render_pdf_refund(refund))
        refund.save()

        self._email_something('invoice_refund.txt',
                              '%s #%s - refunded' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
                              '{0}_refund_{1}.pdf'.format(settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
                              refund.refund_pdf,
                              bcc=True,
                              extracontext={'refund': refund}
        )
        InvoiceHistory(invoice=self.invoice, txt='Sent refund notice').save()

    def _email_something(self, template_name, mail_subject, pdfname=None, pdfcontents=None, bcc=False, extracontext=None):
        # Send off the receipt/invoice by email if possible
        if not self.invoice.recipient_email:
            return

        # Build a text email, and attach the PDF if there is one
        if self.invoice.recipient_secret:
            # If we have the secret, include it in the email even if we have
            # a user. This is because users often forward that email, and
            # then the recipient can access it. As long as the secret is
            # included, both the logged in and the not logged in user
            # can see it.
            invoiceurl = '%s/invoices/%s/%s/' % (settings.SITEBASE, self.invoice.pk, self.invoice.recipient_secret)
        elif self.invoice.recipient_user:
            # General URL that shows a normal invoice
            invoiceurl = '%s/invoices/%s/' % (settings.SITEBASE, self.invoice.pk)
        else:
            invoiceurl = None

        param = {
            'invoice': self.invoice,
            'invoiceurl': invoiceurl,
            'currency_abbrev': settings.CURRENCY_ABBREV,
            'currency_symbol': settings.CURRENCY_SYMBOL,
        }
        if extracontext:
            param.update(extracontext)

        pdfdata = []
        if pdfname:
            pdfdata = [(pdfname, 'application/pdf', base64.b64decode(pdfcontents)), ]

        if bcc:
            bcclist = [settings.INVOICE_NOTIFICATION_RECEIVER, ]
        else:
            bcclist = []
        if self.invoice.extra_bcc_list:
            bcclist.extend([e.strip() for e in self.invoice.extra_bcc_list.split(',')])

        # Queue up in the database for email sending soon
        send_template_mail(settings.INVOICE_SENDER_EMAIL,
                           self.invoice.recipient_email,
                           mail_subject,
                           'invoices/mail/%s' % template_name,
                           param,
                           pdfdata,
                           bcclist,
                       )


def _standard_logger(message):
    print(message)


def _trunc_string(s, l):
    # Truncate a string to specified length, adding "..." at the end in case
    # it's truncated.
    if len(s) <= l:
        return s

    return s[:97] + "..."


class InvoiceManager(object):
    def __init__(self):
        pass

    RESULT_OK = 0
    RESULT_NOTFOUND = 1
    RESULT_NOTSENT = 2
    RESULT_ALREADYPAID = 3
    RESULT_DELETED = 4
    RESULT_INVALIDAMOUNT = 5
    RESULT_PROCESSORFAIL = 6
    RESULT_NOTMATCHED = 7

    def process_incoming_payment(self, transtext, transamount, transdetails, transcost, incomeaccount, costaccount, extraurls=None, logger=None, method=None):
        # If there is no logger specified, just log with print statement
        if not logger:
            logger = _standard_logger

        # Look for a matching invoice, by transtext. We assume the
        # trantext is "PostgreSQL Europe Invoice #nnn - <whatever>"
        #
        # Transdetails are the ones written to the record as payment
        # details for permanent reference. This can be for example the
        # payment systems transaction id.
        #
        # Transcost is the cost of this transaction. If set to 0, no
        #           accounting row will be written for the cost.
        # Incomeaccount is the account number to debit the income to
        # Costaccount is the account number to credit the cost to
        #
        # The credit of the actual income is already noted on the,
        # invoice since it's not dependent on the payment method.
        #
        # Returns a tuple of (status,invoice,processor)
        #
        m = re.match('^%s #(\d+) .*' % settings.INVOICE_TITLE_PREFIX, transtext)
        if not m:
            return (self.RESULT_NOTMATCHED, None, None)

        try:
            invoiceid = int(m.groups(1)[0])
        except:
            logger("Could not match transaction id from '%s'" % transtext)
            return (self.RESULT_NOTFOUND, None, None)

        try:
            invoice = Invoice.objects.get(pk=invoiceid)
        except Invoice.DoesNotExist:
            logger("Could not find invoice with id '%s'" % invoiceid)
            return (self.RESULT_NOTFOUND, None, None)

        return self.process_incoming_payment_for_invoice(invoice, transamount, transdetails, transcost, incomeaccount, costaccount, extraurls, logger, method)

    def process_incoming_payment_for_invoice(self, invoice, transamount, transdetails, transcost, incomeaccount, costaccount, extraurls, logger, method):
        # Do the same as process_incoming_payment, but assume that the
        # invoice has already been matched by other means.
        invoiceid = invoice.pk

        if not invoice.finalized:
            logger("Invoice %s was never sent!" % invoiceid)
            return (self.RESULT_NOTSENT, None, None)

        if invoice.ispaid:
            logger("Invoice %s already paid!" % invoiceid)
            return (self.RESULT_ALREADYPAID, None, None)

        if invoice.deleted:
            logger("Invoice %s has been deleted!" % invoiceid)
            return (self.RESULT_DELETED, None, None)

        if invoice.total_amount != transamount:
            logger("Invoice %s, received payment of %s, expected %s!" % (invoiceid, transamount, invoice.total_amount))
            return (self.RESULT_INVALIDAMOUNT, None, None)

        # Things look good, flag this invoice as paid
        invoice.paidat = datetime.now()
        invoice.paymentdetails = transdetails[:100]
        invoice.paidusing = method

        # If there is a processor module registered for this invoice,
        # we need to instantiate it and call it. So, well, let's do
        # that.
        processor = None
        if invoice.processor:
            processor = self.get_invoice_processor(invoice, logger=logger)
            if not processor:
                # get_invoice_processor() has already logged
                return (self.RESULT_PROCESSORFAIL, None, None)
            try:
                with transaction.atomic():
                    processor.process_invoice_payment(invoice)
            except Exception as ex:
                logger("Failed to run invoice processor '%s': %s" % (invoice.processor, ex))
                return (self.RESULT_PROCESSORFAIL, None, None)

        # Generate a PDF receipt for this, since it's now paid
        wrapper = InvoiceWrapper(invoice)
        invoice.pdf_receipt = base64.b64encode(wrapper.render_pdf_receipt())

        # Save and we're done!
        invoice.save()

        # Create an accounting entry for this invoice. If we have the required
        # information on the invoice, we can finalize it. If not, we will
        # need to create an open ended one.

        accountingtxt = 'Invoice #%s: %s' % (invoice.id, invoice.title)
        accrows = [
            (incomeaccount, accountingtxt, invoice.total_amount - transcost, None),
            ]
        if transcost > 0:
            # If there was a transaction cost known at this point (which
            # it typically is with Paypal), make sure we book a row for it.
            accrows.append(
                (costaccount, accountingtxt, transcost, invoice.accounting_object),
            )
        if invoice.total_vat:
            # If there was VAT on this invoice, create a separate accounting row for this
            # part. As there can in theory (though maybe not in practice?) be multiple different
            # VATs on the invoice, we need to summarize the rows.
            vatsum = defaultdict(int)
            for r in invoice.invoicerow_set.all():
                if r.vatrate_id:
                    vatsum[r.vatrate.vataccount.num] += (r.rowamount * r.rowcount * r.vatrate.vatpercent / Decimal(100)).quantize(Decimal('0.01'))
            total_vatsum = sum(vatsum.values())
            if invoice.total_vat != total_vatsum:
                raise Exception("Stored VAT total %s does not match calculated %s" % (invoice.total_vat, total_vatsum))

            for accountnum, s in list(vatsum.items()):
                accrows.append(
                    (accountnum, accountingtxt, -s, None),
                )

        if invoice.accounting_account:
            accrows.append(
                (invoice.accounting_account, accountingtxt, -(invoice.total_amount - invoice.total_vat), invoice.accounting_object),
            )
            leaveopen = False
        else:
            leaveopen = True
        urls = ['%s/invoices/%s/' % (settings.SITEBASE, invoice.pk), ]
        if extraurls:
            urls.extend(extraurls)

        create_accounting_entry(date.today(), accrows, leaveopen, urls)

        # Send the receipt to the user if possible - that should make
        # them happy :)
        wrapper.email_receipt()

        # Write a log, because it's always nice..
        InvoiceHistory(invoice=invoice, txt='Processed payment').save()
        InvoiceLog(
            message="Processed payment of %s %s for invoice %s (%s)" % (
                invoice.total_amount,
                settings.CURRENCY_ABBREV,
                invoice.pk,
                invoice.title),
            timestamp=datetime.now()
        ).save()

        return (self.RESULT_OK, invoice, processor)

    def get_invoice_processor(self, invoice, logger=None):
        if invoice.processor:
            try:
                pieces = invoice.processor.classname.split('.')
                modname = '.'.join(pieces[:-1])
                classname = pieces[-1]
                mod = __import__(modname, fromlist=[classname, ])
                return getattr(mod, classname)()
            except Exception as ex:
                if logger:
                    logger("Failed to instantiate invoice processor '%s': %s" % (invoice.processor, ex))
                    return None
                else:
                    raise Exception("Failed to instantiate invoice processor '%s': %s" % (invoice.processor, ex))
        else:
            return None

    # Cancel the specified invoice, calling any processor set on it if necessary
    def cancel_invoice(self, invoice, reason):
        # If this invoice has a processor, we need to start by calling it
        processor = self.get_invoice_processor(invoice)
        if processor:
            try:
                with transaction.atomic():
                    processor.process_invoice_cancellation(invoice)
            except Exception as ex:
                raise Exception("Failed to run invoice processor '%s': %s" % (invoice.processor, ex))

        invoice.deleted = True
        invoice.deletion_reason = reason
        invoice.save()

        InvoiceHistory(invoice=invoice, txt='Canceled').save()

        # Send the receipt to the user if possible - that should make
        # them happy :)
        wrapper = InvoiceWrapper(invoice)
        wrapper.email_cancellation(reason)

        InvoiceLog(timestamp=datetime.now(), message="Deleted invoice %s: %s" % (invoice.id, invoice.deletion_reason)).save()

    def refund_invoice(self, invoice, reason, amount, vatamount, vatrate):
        # Initiate a refund of an invoice if there is a payment provider that supports it.
        # Otherwise, flag the invoice as refunded, and assume the user took care of it manually.

        r = InvoiceRefund(invoice=invoice, reason=reason, amount=amount, vatamount=vatamount, vatrate=vatrate)
        r.save()

        InvoiceHistory(invoice=invoice,
                       txt='Registered refund of {0}{1}'.format(settings.CURRENCY_SYMBOL, amount + vatamount)).save()

        wrapper = InvoiceWrapper(invoice)
        if invoice.can_autorefund:
            # Send an initial notice to the user.
            wrapper.email_refund_initiated(r)

            # Accounting record is created when we send the API call to the
            # provider.

            InvoiceLog(timestamp=datetime.now(),
                       message="Initiated refund of {0}{1} of invoice {2}: {3}".format(settings.CURRENCY_SYMBOL, amount + vatamount, invoice.id, reason),
                   ).save()
        else:
            # No automatic refund, so this is flagging something that has
            # already been done. Update accordingly.
            r.issued = r.registered
            r.completed = r.registered
            r.payment_reference = "MANUAL"
            r.save()

            # Create accounting record, since we flagged it manually. As we
            # don't know which account it was refunded from, leave that
            # end open.
            if invoice.accounting_account:
                accountingtxt = 'Refund of invoice #{0}: {1}'.format(invoice.id, invoice.title)
                accrows = [
                    (invoice.accounting_account, accountingtxt, invoice.total_amount - vatamount, invoice.accounting_object),
                ]
                if vatamount:
                    accrows.append(
                        (r.vatrate.vataccount.num, accountingtxt, vatamount, None),
                    )

                urls = ['%s/invoices/%s/' % (settings.SITEBASE, invoice.pk), ]
                create_accounting_entry(date.today(), accrows, True, urls)

            InvoiceHistory(invoice=invoice,
                           txt='Flagged refund of {0}{1}'.format(settings.CURRENCY_SYMBOL, amount + vatamount)).save()

            wrapper.email_refund_sent(r)
            InvoiceLog(timestamp=datetime.now(),
                       message="Flagged invoice {0} as refunded by {1}{2}: {3}".format(invoice.id, settings.CURRENCY_SYMBOL, amount + vatamount, reason),
                       ).save()

        return r

    def autorefund_invoice(self, refund):
        # Send an API call to initiate a refund
        if refund.invoice.autorefund(refund):
            refund.issued = datetime.now()
            refund.save()

            InvoiceHistory(invoice=refund.invoice, txt='Sent refund request to provider').save()
            return True
        else:
            InvoiceHistory(invoice=refund.invoice, txt='Failed to send refund request to provider').save()
            return False

    def complete_refund(self, refundid, refundamount, refundfee, incomeaccount, costaccount, extraurls, method):
        # Process notification from payment provider that refund has completed
        refund = InvoiceRefund.objects.get(id=refundid)
        invoice = refund.invoice

        if refund.completed:
            raise Exception("Refund {0} has already been completed".format(refundid))
        if not refund.issued:
            raise Exception("Refund {0} has not been issued, yet signaled completed!".format(refundid))

        if -refundamount != refund.amount + refund.vatamount:
            raise Exception("Refund {0} attempted to process amount {1} but refund should be {2}".format(refundid, -refundamount, refund.amount + refund.vatamount))

        accountingtxt = 'Refund ({0}) of invoice #{1}'.format(refundid, invoice.id)
        accrows = [
            (incomeaccount, accountingtxt, -(refundamount - refundfee), None),
        ]
        if refund.vatamount:
            accrows.append(
                (refund.vatrate.vataccount.num, accountingtxt, refund.vatamount, None),
            )
        if refundfee != 0:
            accrows.append(
                (costaccount, accountingtxt, -refundfee, invoice.accounting_object),
            )
        if invoice.accounting_account:
            accrows.append(
                (invoice.accounting_account, accountingtxt, refundamount - refund.vatamount, invoice.accounting_object),
            )
            leaveopen = False
        else:
            leaveopen = True
        urls = ['%s/invoices/%s/' % (settings.SITEBASE, invoice.pk), ]
        if extraurls:
            urls.extend(extraurls)

        create_accounting_entry(date.today(), accrows, leaveopen, urls)

        # Also flag the refund as done
        refund.completed = datetime.now()
        refund.save()

        wrapper = InvoiceWrapper(invoice)
        wrapper.email_refund_sent(refund)

        InvoiceHistory(invoice=invoice, txt='Completed refund {0}'.format(refund.id)).save()

    # This creates a complete invoice, and finalizes it
    def create_invoice(self,
                       recipient_user,
                       recipient_email,
                       recipient_name,
                       recipient_address,
                       title,
                       invoicedate,
                       duedate,
                       invoicerows,
                       paymentmethods,
                       processor=None,
                       processorid=None,
                       accounting_account=None,
                       accounting_object=None,
                       canceltime=None,
                       reverse_vat=False,
                       extra_bcc_list=None):
        invoice = Invoice(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            title=title,
            invoicedate=invoicedate,
            duedate=duedate,
            total_amount=-1,
            accounting_account=accounting_account,
            accounting_object=accounting_object,
            canceltime=canceltime,
            reverse_vat=reverse_vat,
            extra_bcc_list=extra_bcc_list or '')
        if recipient_user:
            invoice.recipient_user = recipient_user
        if processor:
            invoice.processor = processor
        if processorid:
            invoice.processorid = processorid
        # Add our rows. Need to save the invoice first so it has an id.
        # But we expect to be in a transaction anyway.
        invoice.save()
        for r in invoicerows:
            invoice.invoicerow_set.add(InvoiceRow(invoice=invoice,
                                                  rowtext=_trunc_string(r[0], 100),
                                                  rowcount=r[1],
                                                  rowamount=r[2],
                                                  vatrate=r[3],
            ), bulk=False)

        # Add the ways it can be paid
        invoice.allowedmethods = paymentmethods
        invoice.save()

        # That should be it. Finalize so we get a PDF, and then
        # return whatever we have.
        wrapper = InvoiceWrapper(invoice)
        wrapper.finalizeInvoice()
        return invoice

    def postpone_invoice_autocancel(self, invoice, mintime, reason, silent=False):
        # Extend an invoice to be valid at least mintime into the future. Unless
        # silent is set, a notification will be sent to the invoice address if
        # this happens. No notification is sent to the end user.
        if invoice.paidat:
            # Already paid. Could happen if payment notification is delivered concurrently,
            # so just ignore it.
            return False
        if not invoice.canceltime:
            return False
        if invoice.canceltime > datetime.now() + mintime:
            return False

        # Else we need to extend it, so do it
        oldtime = invoice.canceltime
        invoice.canceltime = datetime.now() + mintime
        invoice.save()

        InvoiceHistory(invoice=invoice, txt='Extended until {0}: {1}'.format(invoice.canceltime, reason)).save()

        if not silent:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.INVOICE_NOTIFICATION_RECEIVER,
                             "Invoice {0} automatically extended".format(invoice.id),
                             """The invoice with id {0} has had it's automatic cancel time extended
from {1} to {2}.

The reason for this was:
{3}

The invoice remains active regardless of the original cancel time, and will
keep getting extended until the process is manually stopped. A new notification
will be sent after each extension.
""".format(invoice.id, oldtime, invoice.canceltime, reason))


# This is purely for testing, obviously
class TestProcessor(object):
    def process_invoice_payment(self, invoice):
        print("Callback processing invoice with title '%s', for my own id %s" % (invoice.title, invoice.processorid))

    def process_invoice_cancellation(self, invoice):
        raise Exception("This processor can't cancel invoices.")

    def get_return_url(self, invoice):
        print("Trying to get the return url, but I can't!")
        return "http://unknown.postgresql.eu/"

    def get_admin_url(self, invoice):
        return None


# Calculate the number of workdays between two datetimes.
def diff_workdays(start, end):
    weekdays = len(list(rrule.rrule(rrule.DAILY, byweekday=list(range(0, 5)), dtstart=start, until=end)))

    if end.hour < 8:
        weekdays -= 1
    if start.hour > 17:
        weekdays -= 1

    # We want full days only, so drop one
    weekdays -= 1

    if weekdays < 0:
        weekdays = 0

    return weekdays


def is_managed_bank_account(account):
    # All managed bank account methods have to specify a field for
    # "account" that is the one that they manage. So figure out if
    # one exists for this account.
    # We only look at payment methods that are active, of course
    # NOTE! account is the number of the account, not the Account object!
    return InvoicePaymentMethod.objects.filter(active=True).extra(
        where=["config->>'bankaccount' = %s::text"],
        params=[account],
    ).exists()


def automatch_bank_transaction_rule(trans, matcher):
    # We only do exact matching, fuzzyness is handled elsewhere
    if trans.amount == matcher.amount and re.match(matcher.pattern, trans.transtext, re.I):
        # Flag the journal entry as closed since this transaction now arrived
        if matcher.journalentry.closed:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.INVOICE_NOTIFICATION_RECEIVER,
                             "Bank payment pattern match for closed entry received",
                             "A bank tranksaction of {0}{1} with text\n{2}\nmatched journal entry {3}, but this entry was already closed!\n\nNeeds manual examination!".format(
                                 trans.amount,
                                 settings.CURRENCY_ABBREV,
                                 trans.transtext,
                                 matcher.journalentry,
                             ))

            InvoiceLog(message="Bank transaction of {0}{1} with text {2} matched journal entry {3}, but this entry was already closed!".format(
                trans.amount,
                settings.CURRENCY_ABBREV,
                trans.transtext,
                matcher.journalentry,
            )).save()
        else:
            matcher.journalentry.closed = True
            matcher.journalentry.save()

            InvoiceLog(message="Matched bank transaction of {0}{1} with text {2} to journal entry {3}.".format(
                trans.amount,
                settings.CURRENCY_ABBREV,
                trans.transtext,
                matcher.journalentry,
            )).save()

        return True


# Handle a new bank matcher. If it matches something already in the pending bank transfer
# queue then process it. If not, then stick it in the queue.
def register_pending_bank_matcher(account, pattern, amount, journalentry):
    # Create an object so we can try to match it, but hold off on saving
    # it until we know.
    if not isinstance(account, Account):
        account = Account.objects.get(num=account)
    if not isinstance(amount, Decimal):
        raise Exception("Amount must be specified as Decimal!")

    matcher = PendingBankMatcher(pattern=pattern,
                                 amount=amount,
                                 foraccount=account,
                                 journalentry=journalentry)

    # Run the matcher across all pending banktransactions
    for bt in PendingBankTransaction.objects.all():
        if automatch_bank_transaction_rule(bt, matcher):
            # The matcher object is never saved, but remove the pending
            # bank transaction since it is now "used".
            bt.delete()
            return

    # Not found, so save it for future matching (normal case, since banks
    # tend to deliver their information slower).
    matcher.save()


# Handle a new bank transaction that has arrived. If it matches an invoice or
# an existing BankMatcher, process that one immediately. If not, stick it on
# the list of pending ones.
# Returns true if the transaction was immediately matched to something and needs
# no further processing.
def register_bank_transaction(method, methodidentifier, amount, transtext, sender, canreturn=False):
    if not isinstance(amount, Decimal):
        raise Exception("Amount must be specified as Decimal!")

    # First try to match it against pending invoices.
    # We search by amount and then match by payment reference as our primary choice.
    for invoice in Invoice.objects.filter(finalized=True,
                                          deleted=False,
                                          paidat__isnull=True,
                                          total_amount=amount):
        if invoice.payment_reference in transtext.replace(' ', ''):
            # We have a match!
            pm = method.get_implementation()

            invoicelog = io.StringIO()
            invoicelog.write("Invoice {0} matched but processing failed:\n".format(invoice.id))

            def invoicelogger(msg):
                invoicelog.write(msg)
                invoicelog.write("\n")

            manager = InvoiceManager()
            (status, _invoice, _processor) = manager.process_incoming_payment_for_invoice(
                invoice,
                amount,
                "Bank transfer from {0} with id {1}".format(method.internaldescription, methodidentifier),
                0,  # No fees on bank transfers supported
                pm.config('bankaccount'),
                0,   # No fees, so no fees account
                [],  # No URLs supported
                invoicelogger,
                method)

            if status != manager.RESULT_OK:
                # Payment failed somehow. In this case we leave the transaction as a
                # pending transaction, and have the operator clean it up.
                PendingBankTransaction(method=method,
                                       methodidentifier=methodidentifier,
                                       created=datetime.now(),
                                       amount=amount,
                                       transtext=transtext,
                                       sender=sender,
                                       comments=invoicelog.getvalue(),
                                       canreturn=canreturn and amount > 0,
                ).save()

                InvoiceLog(message="Bank payment '{0}' matched invoice {1}, but processing failed".format(
                    transtext,
                    invoice.id,
                )).save()

                return False  # Needs more preocessing since we failed

            # On success, send a notification
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.INVOICE_NOTIFICATION_RECEIVER,
                             "Bank transfer payment confirmed",
                             "A bank transfer payment from {0} matched an invoice.\nInvoice: {1}\nAmount: {2}\nRecipient name: {3}\nRecipient user: {4}\n".format(
                                 method.internaldescription,
                                 invoice.title,
                                 invoice.total_amount,
                                 invoice.recipient_name,
                                 invoice.recipient_email,
                             ))

            InvoiceLog(message="Bank payment reference '{0}' matched invoice {1}".format(transtext, invoice.id)).save()

            # Invoice processed immediately and we haven't stored the transaction
            # yet, so just consider it done.
            return True

    # If no invoices are found, then try to match it against the pending
    # bank matchers. (Check this later because it's a it more expensive)

    # Create an object so we can try to match it, but hold off on saving
    # it until we know.
    trans = PendingBankTransaction(method=method,
                                   methodidentifier=methodidentifier,
                                   created=datetime.now(),
                                   amount=amount,
                                   transtext=transtext,
                                   sender=sender,
                                   canreturn=canreturn and amount > 0,
    )

    for matcher in PendingBankMatcher.objects.all():
        if automatch_bank_transaction_rule(trans, matcher):
            matcher.delete()
            return True

    # Not found, so save it for future matching (probably going to end up manual)
    trans.save()

    # More processing needed later, so return False
    return False
