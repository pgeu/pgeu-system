from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.safestring import mark_safe
from django.utils import timezone

from decimal import Decimal

from .payment import PaymentMethodWrapper

from postgresqleu.util.validators import ListOfEmailAddressValidator
from postgresqleu.util.checksum import luhn
from postgresqleu.util.fields import LowercaseEmailField, NormalizedDecimalField
from postgresqleu.accounting.models import Account, JournalEntry


class InvoiceProcessor(models.Model):
    # The processor name is purely cosmetic
    processorname = models.CharField(max_length=50, null=False, blank=False, unique=True)
    # Python class name (full path) to the class that should be
    # notified when an invoice has been processed.
    classname = models.CharField(max_length=200, null=False, blank=False)

    def __str__(self):
        return self.processorname


class InvoicePaymentMethod(models.Model):
    name = models.CharField(max_length=100, null=False, blank=False, help_text="Name used on public site")
    active = models.BooleanField(null=False, blank=False, default=False)
    sortkey = models.IntegerField(null=False, blank=False, default=100, verbose_name="Sort key")
    internaldescription = models.CharField(max_length=100, null=False, blank=True,
                                           verbose_name="Internal name",
                                           help_text="Name used in admin pages and configuration")
    # Python class name (full path) to the class that implements
    # this payment method.
    classname = models.CharField(max_length=200, null=False, blank=False, verbose_name="Implementation class")
    config = models.JSONField(blank=False, null=False, default=dict)
    status = models.JSONField(blank=False, null=False, default=dict, encoder=DjangoJSONEncoder)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['sortkey', ]

    def get_implementation(self):
        pieces = self.classname.split('.')
        modname = '.'.join(pieces[:-1])
        classname = pieces[-1]
        mod = __import__(modname, fromlist=[classname, ])
        return getattr(mod, classname)(self.id, self)

    def upload_tooltip(self):
        return mark_safe(self.get_implementation().upload_tooltip)


class InvoiceRefund(models.Model):
    invoice = models.ForeignKey("Invoice", null=False, blank=False, on_delete=models.CASCADE)
    reason = models.CharField(max_length=500, null=False, blank=True, default='', help_text="Reason for refunding of invoice")

    amount = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    vatamount = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    vatrate = models.ForeignKey('VatRate', null=True, blank=True, on_delete=models.CASCADE)

    registered = models.DateTimeField(null=False, auto_now_add=True)
    issued = models.DateTimeField(null=True, blank=True)
    completed = models.DateTimeField(null=True, blank=True)

    payment_reference = models.CharField(max_length=100, null=False, blank=True, help_text="Reference in payment system, depending on system used for invoice.")

    refund_pdf = models.TextField(blank=True, null=False)

    class Meta:
        ordering = ('id', )

    @property
    def fullamount(self):
        return self.amount + self.vatamount


class Invoice(models.Model):
    # pk = invoice number, which is fully exposed.

    # The recipient. We set the user if we have matched it to an
    # account, but support invoices that are just listed
    # by name. If email is set, we can retro-match it up, but once
    # a recipient is matched, the recipient_user field "owns" the
    # recipient information.
    recipient_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    recipient_email = LowercaseEmailField(blank=True, null=False)
    recipient_name = models.CharField(max_length=100, blank=False, null=False)
    recipient_address = models.TextField(blank=False, null=False)
    recipient_secret = models.CharField(max_length=64, blank=True, null=True)
    extra_bcc_list = models.CharField(max_length=500, blank=True, null=False, validators=[ListOfEmailAddressValidator, ])

    # Global invoice info
    title = models.CharField(max_length=100, blank=False, null=False, verbose_name="Invoice title")
    extradescription = models.TextField(blank=True, null=False, verbose_name="Extra description")
    invoicedate = models.DateTimeField(null=False, blank=False)
    duedate = models.DateTimeField(null=False, blank=False)
    canceltime = models.DateTimeField(null=True, blank=True, help_text="Invoice will automatically be canceled at this time")

    # Amount information is calculated when the invoice is finalized
    total_amount = models.DecimalField(decimal_places=2, max_digits=10, null=False)
    total_vat = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0)
    reverse_vat = models.BooleanField(null=False, blank=False, default=False, help_text="Invoice is subject to EU reverse VAT")

    finalized = models.BooleanField(null=False, blank=True, default=False, help_text="Invoice is finalized, should not ever be changed again")
    deleted = models.BooleanField(null=False, blank=False, default=False, help_text="This invoice has been deleted")
    deletion_reason = models.CharField(max_length=500, null=False, blank=True, default='', help_text="Reason for deletion of invoice")

    # base64 encoded version of the PDF invoice
    pdf_invoice = models.TextField(blank=True, null=False)

    # Which class, if any, is responsible for processing the payment
    # of this invoice. This can typically be to flag a conference
    # payment as done once the payment is in. processorid is an arbitrary
    # id value that the processor can use for whatever it wants.
    processor = models.ForeignKey(InvoiceProcessor, null=True, blank=True, on_delete=models.CASCADE)
    processorid = models.IntegerField(null=True, blank=True)

    # Allowed payment methods
    allowedmethods = models.ManyToManyField(InvoicePaymentMethod, blank=True, verbose_name="Allowed payment methods")

    # Payment status of this invoice. Once it's paid, the payment system
    # writes the details of the transaction to the paymentdetails field.
    paidat = models.DateTimeField(null=True, blank=True)
    paymentdetails = models.CharField(max_length=100, null=False, blank=True)
    paidusing = models.ForeignKey(InvoicePaymentMethod, null=True, blank=True, related_name="paidusing", verbose_name="Payment method actually used", on_delete=models.CASCADE)

    # Reminder (if any) sent when?
    remindersent = models.DateTimeField(null=True, blank=True, verbose_name="Automatic reminder sent at")

    # Once an invoice is paid, a recipient is generated. PDF base64
    pdf_receipt = models.TextField(blank=True, null=False)

    # Information for accounting of this invoice. This is intentionally not
    # foreign keys - we'll just drop some such information into the system
    # manually in the forms.
    accounting_account = models.IntegerField(null=True, blank=True, verbose_name="Accounting account")
    accounting_object = models.CharField(null=True, blank=True, max_length=30, verbose_name="Accounting object")

    @property
    def has_recipient_user(self):
        return self.recipientuser and True or False

    @property
    def ispaid(self):
        return self.paidat is not None

    @property
    def isexpired(self):
        return (self.paidat is None) and self.duedate and (self.duedate < timezone.now())

    @property
    def allowedmethodwrappers(self):
        return [PaymentMethodWrapper(m, self) for m in self.allowedmethods.filter(active=True)]

    @property
    def invoicestr(self):
        return "%s #%s - %s" % (settings.INVOICE_TITLE_PREFIX, self.pk, self.title)

    @property
    def payment_fees(self):
        if self.paidusing:
            return PaymentMethodWrapper(self.paidusing, self).payment_fees
        else:
            return "unknown"

    @property
    def amount_without_fees(self):
        f = self.payment_fees
        if type(f) == str:
            return "Unknown"
        else:
            return self.total_amount - f

    @property
    def amount_without_vat(self):
        return self.total_amount - self.total_vat

    def used_vatrates(self):
        return ", ".join([str(r.vatrate) for r in self.invoicerow_set.all() if r.vatrate])

    @property
    def can_autorefund(self):
        return PaymentMethodWrapper(self.paidusing, self).can_autorefund

    def autorefund(self, refund):
        return PaymentMethodWrapper(self.paidusing, self).autorefund(refund)

    @property
    def total_refunds(self):
        agg = self.invoicerefund_set.all().aggregate(models.Sum('amount'), models.Sum('vatamount'))
        return {
            'amount': agg['amount__sum'] or 0,
            'vatamount': agg['vatamount__sum'] or 0,
            'remaining': {
                'amount': self.total_amount - self.total_vat - (agg['amount__sum'] or 0),
                'vatamount': self.total_vat - (agg['vatamount__sum'] or 0),
            }
        }

    @property
    def payment_method_description(self):
        if not self.paidat:
            return "not paid"
        if self.paidusing:
            return "paid using {0}.".format(self.paidusing.internaldescription)
        return "manually flagged as paid."

    @property
    def statusstring(self):
        if self.deleted:
            return "canceled"
        elif self.paidat:
            return "paid"
        if self.finalized:
            return "finalized"
        else:
            return "pending"

    @property
    def payment_reference(self):
        ref = "{0}{1:05d}".format(str(int(self.invoicedate.timestamp()))[-4:], self.id)
        return ref + str(luhn(ref))

    def __str__(self):
        return "Invoice #%s" % self.pk

    class Meta:
        ordering = ('-id', )


class VatRate(models.Model):
    name = models.CharField(max_length=100, blank=False, null=False)
    shortname = models.CharField(max_length=16, blank=False, null=False, verbose_name="Short name")
    vatpercent = NormalizedDecimalField(null=False, default=0, verbose_name="VAT percentage", max_digits=9, decimal_places=6, validators=[MaxValueValidator(100), MinValueValidator(0)])
    vataccount = models.ForeignKey(Account, null=False, blank=False, on_delete=models.CASCADE, verbose_name="VAT account")
    _safe_attributes = ('vatpercent', 'shortstr', 'shortname', 'name')

    def __str__(self):
        return "{0} ({1}%)".format(self.name, self.vatpercent)

    @property
    def shortstr(self):
        return "%s%% (%s)" % (self.vatpercent, self.shortname)


class VatValidationCache(models.Model):
    vatnumber = models.CharField(max_length=100, null=False, blank=False)
    checkedat = models.DateTimeField(null=False, blank=False, auto_now_add=True)


class InvoiceRow(models.Model):
    # Invoice rows are only used up until the invoice is finished,
    # but allows us to save a half-finished invoice.
    invoice = models.ForeignKey(Invoice, null=False, on_delete=models.CASCADE)
    rowtext = models.CharField(max_length=100, blank=False, null=False, verbose_name="Text")
    rowcount = models.IntegerField(null=False, default=1, verbose_name="Count")
    rowamount = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, verbose_name="Amount per item (ex VAT)")
    vatrate = models.ForeignKey(VatRate, null=True, on_delete=models.CASCADE)

    def __str__(self):
        return self.rowtext

    @property
    def totalvat(self):
        if self.vatrate:
            return (self.rowamount * self.rowcount * self.vatrate.vatpercent / Decimal(100)).quantize(Decimal('.01'))
        else:
            return 0

    @property
    def totalrow(self):
        return self.rowamount * self.rowcount

    @property
    def totalwithvat(self):
        return self.totalrow + self.totalvat


class InvoiceHistory(models.Model):
    invoice = models.ForeignKey(Invoice, null=False, on_delete=models.CASCADE)
    time = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    txt = models.CharField(max_length=2000, null=False, blank=False)

    class Meta:
        ordering = ['time', ]

    def __str__(self):
        return self.txt


class InvoiceLog(models.Model):
    timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    message = models.TextField(null=False, blank=False)
    sent = models.BooleanField(null=False, blank=False, default=False)

    @property
    def message_trunc(self):
        return self.message[:150]

    class Meta:
        ordering = ['-timestamp', ]


class PendingBankTransaction(models.Model):
    method = models.ForeignKey(InvoicePaymentMethod, null=False, blank=False, on_delete=models.CASCADE)
    methodidentifier = models.IntegerField(null=False, blank=False)
    created = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    transtext = models.CharField(max_length=500, null=False, blank=True)
    sender = models.CharField(max_length=1000, null=False, blank=True)
    comments = models.TextField(max_length=2000, null=False, blank=True)
    canreturn = models.BooleanField(null=False, blank=False, default=False)


class PendingBankMatcher(models.Model):
    created = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    pattern = models.CharField(max_length=200, null=False, blank=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    foraccount = models.ForeignKey(Account, null=False, blank=False, on_delete=models.CASCADE)
    journalentry = models.ForeignKey(JournalEntry, null=False, blank=False, on_delete=models.CASCADE)


class BankTransferFees(models.Model):
    invoice = models.ForeignKey(Invoice, null=False, blank=False, on_delete=models.CASCADE)
    fee = models.DecimalField(max_digits=10, decimal_places=2, null=False)


class BankFileUpload(models.Model):
    method = models.ForeignKey(InvoicePaymentMethod, null=False, blank=False, on_delete=models.CASCADE)
    created = models.DateTimeField(null=False, blank=False, auto_now_add=True, db_index=True)
    parsedrows = models.IntegerField(null=False, blank=False)
    newtrans = models.IntegerField(null=False, blank=False)
    newpending = models.IntegerField(null=False, blank=False)
    errors = models.IntegerField(null=False, blank=False)
    uploadby = models.CharField(max_length=50, null=False, blank=False)
    name = models.CharField(max_length=200, null=False, blank=True)
    textcontents = models.TextField(max_length=100000, null=False, blank=False)

    class Meta:
        unique_together = (
            ('method', 'created'),
        )


class BankStatementRow(models.Model):
    method = models.ForeignKey(InvoicePaymentMethod, null=False, blank=False, on_delete=models.CASCADE)
    created = models.DateTimeField(null=False, blank=False, auto_now_add=True, db_index=True)
    fromfile = models.ForeignKey(BankFileUpload, null=True, blank=True, on_delete=models.CASCADE)

    uniqueid = models.TextField(null=True, blank=True)
    date = models.DateField(null=False, blank=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=False, blank=False)
    description = models.CharField(max_length=300, null=False, blank=False)
    balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    other = models.JSONField(blank=False, null=False, default=dict, encoder=DjangoJSONEncoder)

    class Meta:
        unique_together = (
            ('uniqueid', 'method'),
        )
        index_together = (
            ('method', 'date'),
        )
