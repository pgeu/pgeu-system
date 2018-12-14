from django.conf import settings

from datetime import datetime, timedelta, date
import base64
import os

from postgresqleu.mailqueue.util import send_simple_mail, send_template_mail
from postgresqleu.invoices.util import InvoiceManager

from models import Sponsor, PurchasedVoucher
from postgresqleu.confreg.models import PrepaidBatch, PrepaidVoucher
import postgresqleu.invoices.models as invoicemodels

def confirm_sponsor(sponsor, who):
    # Confirm a sponsor, including sending the confirmation email.
    # This will save the specified sponsor model as well, but the function
    # expects to be wrapped in external transaction handler.
    sponsor.confirmed = True
    sponsor.confirmedat = datetime.now()
    sponsor.confirmedby = who
    sponsor.save()

    for manager in sponsor.managers.all():
        send_template_mail(sponsor.conference.sponsoraddr,
                           manager.email,
                           u"[{0}] Sponsorship confirmed".format(sponsor.conference),
                           'confsponsor/mail/sponsor_confirmed.txt',
                           {
                               'sponsor': sponsor,
                               'conference': sponsor.conference,
                           },
                           sendername=sponsor.conference.conferencename,
                           receivername=u'{0} {1}'.format(manager.first_name, manager.last_name))


class InvoiceProcessor(object):
    # Process invoices for sponsorship (this should include both automatic
    # and manual invoices, as long as they are created through the system)
    def process_invoice_payment(self, invoice):
        try:
            sponsor = Sponsor.objects.get(pk=invoice.processorid)
        except Sponsor.DoesNotExist:
            raise Exception("Could not find conference sponsor %s" % invoice.processorid)

        if sponsor.confirmed:
            # This sponsorship was already confirmed. Typical case for this is the contract
            # was signed manually, and then the invoice was generated. In this case, we just
            # don't care, so we return without updating the date of the confirmation.
            return

        confirm_sponsor(sponsor, "Invoice payment")

        conference = sponsor.conference

        send_simple_mail(conference.sponsoraddr,
                         conference.sponsoraddr,
                         "Confirmed sponsor: %s" % sponsor.name,
                         "The sponsor\n%s\nhas completed payment of the sponsorship invoice,\nand is now activated.\nBenefits are not claimed yet." % sponsor.name,
                         sendername=conference.conferencename)

    # An invoice was canceled.
    def process_invoice_cancellation(self, invoice):
        try:
            sponsor = Sponsor.objects.get(pk=invoice.processorid)
        except Sponsor.DoesNotExist:
            raise Exception("Could not find conference sponsor %s" % invoice.processorid)

        if sponsor.confirmed:
            raise Exception("Cannot cancel this invoice, the sponsorship has already been marked as confirmed!")

        # Else the sponsor is not yet confirmed, so we can safely remove the invoice. We will leave the
        # sponsorship registration in place, so we can create a new one if we have to.
        sponsor.invoice = None
        sponsor.save()

    # An invoice was refunded. Actually undoing everything from here
    # is very complicated (e.g. what do we do with attendee vouchers
    # that have already been used?). Because of that, punt that whole
    # thing and just send an email about it instead, letting the
    # operator deal with it.
    # All we'll do is unconfirm the sponsor itself.
    def process_invoice_refund(self, invoice):
        try:
            sponsor = Sponsor.objects.get(pk=invoice.processorid)
        except Sponsor.DoesNotExist:
            raise Exception("Could not find conference sponsorship %s" % invoice.processorid)

        sponsor.confirmed = False
        sponsor.confirmedat = None
        sponsor.confirmedby = "Unconfirmed by refund"
        sponsor.save()

        msgtxt = "The invoice for sponsors {0} has been refunded.\n\nYou need to manually 'undo' any benefits\nthat this sponsor has received, in case that is intended.\n\n".format(sponsor)

        for a in sponsor.conference.sponsoraddr, settings.INVOICE_SENDER_EMAIL:
            send_simple_mail(sponsor.conference.sponsoraddr,
                             a,
                             u"Sponsor {0} refunded!".format(sponsor),
                             msgtxt,
                             sendername=sponsor.conference.conferencename)


    # Return the user to the sponsor page if they have paid.
    def get_return_url(self, invoice):
        try:
            sponsor = Sponsor.objects.get(pk=invoice.processorid)
        except Sponsor.DoesNotExist:
            raise Exception("Could not find conference sponsorship %s" % invoice.processorid)
        return "%s/events/sponsor/%s/" % (settings.SITEBASE, sponsor.id)


def get_sponsor_invoice_address(name, invoiceaddr, vatnumber):
    if settings.EU_VAT and vatnumber:
        return u"{0}\n{1}\n\nVAT: {2}".format(name, invoiceaddr, vatnumber)
    else:
        return u"{0}\n{1}".format(name, invoiceaddr)

# Generate an invoice for sponsorship
def create_sponsor_invoice(user, sponsor):
    conference = sponsor.conference
    level = sponsor.level

    if settings.EU_VAT:
        # If a sponsor has an EU VAT Number, we do *not* charge VAT.
        # For any sponsor without a VAT number, charge VAT.
        # Except if the sponsor is from outside the EU, in which case no VAT.
        # If a sponsor is from our home country, meaning they have a
        #  VAT number and it starts with our prefix, charge VAT.
        # XXX: we should probably have *accounting* entries for reverse
        #      VAT on the ones with a number, but EU vat is currently
        #      handled manually outside the process for now.
        if sponsor.vatstatus == 0:
            # Sponsor inside EU with VAT number
            if not sponsor.vatnumber:
                raise Exception("Cannot happen")
            if sponsor.vatnumber.startswith(settings.EU_VAT_HOME_COUNTRY):
                # Home country, so we charge vat
                vatlevel = conference.vat_sponsorship
                reverse_vat = False
            else:
                # Not home country but has VAT number
                vatlevel = None
                reverse_vat = True
        elif sponsor.vatstatus == 1:
            # Sponsor inside EU but no VAT number
            vatlevel = conference.vat_sponsorship
            reverse_vat = False
        else:
            # Sponsor outside EU
            vatlevel = None
            reverse_vat = False
    else:
        # Not caring about EU VAT, so assign whatever the conference said
        vatlevel = conference.vat_sponsorship
        reverse_vat = False

    invoicerows = [
        ['%s %s sponsorship' % (conference, level), 1, level.levelcost, vatlevel],
    ]
    if conference.startdate < date.today() + timedelta(days=5):
        # If conference happens in the next 5 days, invoice is due immediately
        duedate = date.today()
    elif conference.startdate < date.today() + timedelta(days=30):
        # Less than 30 days before the conference, set the due date to
        # 5 days before the conference
        duedate = conference.startdate - timedelta(days=5)
    else:
        # More than 30 days before the conference, set the due date
        # to 30 days from now.
        duedate = datetime.now() + timedelta(days=30)

    manager = InvoiceManager()
    processor = invoicemodels.InvoiceProcessor.objects.get(processorname="confsponsor processor")
    i = manager.create_invoice(
        user,
        user.email,
        user.first_name + ' ' + user.last_name,
        get_sponsor_invoice_address(sponsor.name, sponsor.invoiceaddr, sponsor.vatnumber),
        '%s sponsorship' % conference.conferencename,
        datetime.now(),
        duedate,
        invoicerows,
        processor=processor,
        processorid=sponsor.pk,
        bankinfo=True,
        accounting_account=settings.ACCOUNTING_CONFSPONSOR_ACCOUNT,
        accounting_object=conference.accounting_object,
        autopaymentoptions=False,
        reverse_vat=reverse_vat,
    )
    i.allowedmethods = level.paymentmethods.all()
    return i


class VoucherInvoiceProcessor(object):
    # Process invoices for sponsor-ordered prepaid vouchers. This includes
    # actually creating the vouchers as necessary.
    def process_invoice_payment(self, invoice):
        try:
            pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
        except PurchasedVoucher.DoesNotExist:
            raise Exception("Could not find voucher order %s" % invoice.processorid)

        if pv.batch:
            raise Exception("This voucher order has already been processed: %s" % invoice.processorid)

        # Set up the batch
        batch = PrepaidBatch(conference=pv.sponsor.conference,
                             regtype=pv.regtype,
                             buyer=pv.user,
                             buyername="{0} {1}".format(pv.user.first_name, pv.user.last_name),
                             sponsor=pv.sponsor)
        batch.save()

        for n in range(0, pv.num):
            v = PrepaidVoucher(conference=pv.sponsor.conference,
                               vouchervalue=base64.b64encode(os.urandom(37)).rstrip('='),
                               batch=batch)
            v.save()

        pv.batch = batch
        pv.save()

        send_simple_mail(pv.sponsor.conference.sponsoraddr,
                         pv.sponsor.conference.sponsoraddr,
                         "Sponsor %s purchased vouchers" % pv.sponsor.name,
                         "The sponsor\n%s\nhas purchased %s vouchers of type \"%s\".\n\n" % (pv.sponsor.name, pv.num, pv.regtype.regtype),
                         sendername=pv.sponsor.conference.conferencename)

    # An invoice was canceled.
    def process_invoice_cancellation(self, invoice):
        try:
            pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
        except PurchasedVoucher.DoesNotExist:
            raise Exception("Could not find voucher order %s" % invoice.processorid)

        if pv.batch:
            raise Exception("Cannot cancel this invoice, the order has already been processed!")

        # Order not confirmed yet, so we can just remove it
        pv.delete()

    # Return the user to the sponsor page if they have paid.
    def get_return_url(self, invoice):
        try:
            pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
        except PurchasedVoucher.DoesNotExist:
            raise Exception("Could not find voucher order %s" % invoice.processorid)
        return "%s/events/sponsor/%s/" % (settings.SITEBASE, pv.sponsor.id)


# Generate an invoice for prepaid vouchers
def create_voucher_invoice(sponsor, user, rt, num):
    invoicerows = [
        ['Voucher for "%s"' % rt.regtype, num, rt.cost, rt.conference.vat_registrations]
        ]

    manager = InvoiceManager()
    processor = invoicemodels.InvoiceProcessor.objects.get(processorname="confsponsor voucher processor")
    i = manager.create_invoice(
        user,
        user.email,
        user.first_name + ' ' + user.last_name,
        sponsor.invoiceaddr,
        'Prepaid vouchers for %s' % sponsor.conference.conferencename,
        datetime.now(),
        date.today(),
        invoicerows,
        processor=processor,
        bankinfo=False,
        accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
        accounting_object=sponsor.conference.accounting_object,
        autopaymentoptions=True
    )
    return i
