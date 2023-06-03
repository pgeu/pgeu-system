from django.utils import timezone
from django.conf import settings

from datetime import datetime, timedelta
import base64
import os

from postgresqleu.invoices.util import InvoiceManager, InvoiceWrapper
from postgresqleu.util.time import today_conference

from .models import Sponsor, PurchasedVoucher
from .util import send_conference_sponsor_notification, send_sponsor_manager_email
from .util import get_mails_for_sponsor
from postgresqleu.confreg.models import PrepaidBatch, PrepaidVoucher
from postgresqleu.confreg.util import send_conference_mail
from postgresqleu.digisign.util import DigisignHandlerBase
import postgresqleu.invoices.models as invoicemodels


def confirm_sponsor(sponsor, who):
    # Confirm a sponsor, including sending the confirmation email.
    # This will save the specified sponsor model as well, but the function
    # expects to be wrapped in external transaction handler.
    sponsor.confirmed = True
    sponsor.confirmedat = timezone.now()
    sponsor.confirmedby = who
    sponsor.save()

    send_sponsor_manager_email(
        sponsor,
        "Sponsorship confirmed",
        'confsponsor/mail/sponsor_confirmed.txt',
        {
            'sponsor': sponsor,
            'conference': sponsor.conference,
        },
    )

    mails = list(get_mails_for_sponsor(sponsor).defer('message'))
    if mails:
        # Emails have been sent to this sponsorship level (only the level
        # will match for a brand new sponsor), so send off an email to the
        # sponsor letting them know what has already been sent.
        send_sponsor_manager_email(
            sponsor,
            "Previous sponsor emails sent",
            'confsponsor/mail/sponsor_confirmed_oldemails.txt',
            {
                'sponsor': sponsor,
                'conference': sponsor.conference,
                'mails': mails,
            },
        )


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

        send_conference_sponsor_notification(
            conference,
            "Confirmed sponsor: %s" % sponsor.name,
            "The sponsor\n%s\nhas completed payment of the sponsorship invoice,\nfor level %s and is now activated.\nBenefits are not claimed yet." % (sponsor.name, sponsor.level),
        )

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

    # Return the user to the sponsor page if they have paid.
    def get_return_url(self, invoice):
        try:
            sponsor = Sponsor.objects.get(pk=invoice.processorid)
        except Sponsor.DoesNotExist:
            raise Exception("Could not find conference sponsorship %s" % invoice.processorid)
        return "%s/events/sponsor/%s/" % (settings.SITEBASE, sponsor.id)

    def get_admin_url(self, invoice):
        try:
            sponsor = Sponsor.objects.get(pk=invoice.processorid)
        except Sponsor.DoesNotExist:
            return None
        return "/events/sponsor/admin/{0}/{1}/".format(sponsor.conference.urlname, sponsor.pk)


def get_sponsor_invoice_address(name, invoiceaddr, vatnumber):
    if settings.EU_VAT and vatnumber:
        return "{0}\n{1}\n\nVAT: {2}".format(name, invoiceaddr, vatnumber)
    else:
        return "{0}\n{1}".format(name, invoiceaddr)


def _invoicerows_for_sponsor(sponsor):
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
                vatlevel = sponsor.conference.vat_sponsorship
                reverse_vat = False
            else:
                # Not home country but has VAT number
                vatlevel = None
                reverse_vat = True
        elif sponsor.vatstatus == 1:
            # Sponsor inside EU but no VAT number
            vatlevel = sponsor.conference.vat_sponsorship
            reverse_vat = False
        else:
            # Sponsor outside EU
            vatlevel = None
            reverse_vat = False
    else:
        # Not caring about EU VAT, so assign whatever the conference said
        vatlevel = sponsor.conference.vat_sponsorship
        reverse_vat = False

    invoicerows = [
        ['%s %s sponsorship' % (sponsor.conference, sponsor.level), 1, sponsor.level.levelcost, vatlevel],
    ]

    return invoicerows, reverse_vat


def get_sponsor_invoice_rows(sponsor):
    return _invoicerows_for_sponsor(sponsor)[0]


# Generate an invoice for sponsorship
def create_sponsor_invoice(user, sponsor, override_duedate=None):
    conference = sponsor.conference
    level = sponsor.level

    invoicerows, reverse_vat = _invoicerows_for_sponsor(sponsor)

    if override_duedate:
        duedate = override_duedate
    elif conference.startdate < today_conference() + timedelta(days=5):
        # If conference happens in the next 5 days, invoice is due immediately
        duedate = timezone.now()
    elif conference.startdate < today_conference() + timedelta(days=30):
        # Less than 30 days before the conference, set the due date to
        # 5 days before the conference
        duedate = timezone.make_aware(datetime.combine(
            conference.startdate - timedelta(days=5),
            timezone.now().time()
        ))
    else:
        # More than 30 days before the conference, set the due date
        # to 30 days from now.
        duedate = timezone.now() + timedelta(days=30)

    manager = InvoiceManager()
    processor = invoicemodels.InvoiceProcessor.objects.get(processorname="confsponsor processor")
    i = manager.create_invoice(
        user,
        user.email,
        user.first_name + ' ' + user.last_name,
        get_sponsor_invoice_address(sponsor.name, sponsor.invoiceaddr, sponsor.vatnumber),
        '%s sponsorship' % conference.conferencename,
        timezone.now(),
        duedate,
        invoicerows,
        processor=processor,
        processorid=sponsor.pk,
        accounting_account=settings.ACCOUNTING_CONFSPONSOR_ACCOUNT,
        accounting_object=conference.accounting_object,
        reverse_vat=reverse_vat,
        extra_bcc_list=conference.sponsoraddr,
        paymentmethods=level.paymentmethods.all(),
    )
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
        batch = PrepaidBatch(conference=pv.conference,
                             regtype=pv.regtype,
                             buyer=pv.user,
                             buyername="{0} {1}".format(pv.user.first_name, pv.user.last_name),
                             sponsor=pv.sponsor)
        batch.save()

        for n in range(0, pv.num):
            v = PrepaidVoucher(conference=pv.conference,
                               vouchervalue=base64.b64encode(os.urandom(37)).rstrip(b'=').decode('utf8'),
                               batch=batch)
            v.save()

        pv.batch = batch
        pv.save()

        if pv.sponsor:
            send_conference_sponsor_notification(
                pv.conference,
                "Sponsor %s purchased vouchers" % pv.sponsor.name,
                "The sponsor\n%s\nhas purchased %s vouchers of type \"%s\".\n\n" % (pv.sponsor.name, pv.num, pv.regtype.regtype),
            )
        else:
            # For non-sponsors, there is no dashboard available, so we send the actual vouchers in an
            # email directly.
            send_conference_mail(pv.conference,
                                 pv.batch.buyer.email,
                                 "Entry vouchers to {}".format(pv.conference.conferencename),
                                 'confreg/mail/prepaid_vouchers.txt',
                                 {
                                     'batch': batch,
                                     'vouchers': batch.prepaidvoucher_set.all(),
                                     'conference': pv.conference,
                                 },
                                 sender=pv.conference.contactaddr,
            )

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
        if pv.sponsor:
            return "%s/events/sponsor/%s/" % (settings.SITEBASE, pv.sponsor.id)
        else:
            return "{0}/events/{1}/prepaid/{2}/".format(settings.SITEBASE, pv.conference.urlname, pv.batch.id)

    def get_admin_url(self, invoice):
        try:
            pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
        except PurchasedVoucher.DoesNotExist:
            return None
        if pv.sponsor:
            return "/events/sponsor/admin/{0}/{1}/".format(pv.conference.urlname, pv.sponsor.id)
        else:
            return "/events/admin/{0}/prepaidorders/".format(pv.conference.urlname)


# Generate an invoice for prepaid vouchers
def create_voucher_invoice(conference, invoiceaddr, user, rt, num):
    invoicerows = [
        ['Voucher for "%s"' % rt.regtype, 1, rt.cost, rt.conference.vat_registrations]
    ] * num

    manager = InvoiceManager()
    processor = invoicemodels.InvoiceProcessor.objects.get(processorname="confsponsor voucher processor")
    i = manager.create_invoice(
        user,
        user.email,
        user.first_name + ' ' + user.last_name,
        invoiceaddr,
        'Prepaid vouchers for %s' % conference.conferencename,
        timezone.now(),
        timezone.now(),
        invoicerows,
        processor=processor,
        accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
        accounting_object=conference.accounting_object,
        paymentmethods=conference.paymentmethods.all(),
    )
    return i


# Handle digital signatures on contracts
class SponsorDigisignHandler(DigisignHandlerBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self.doc, 'sponsor'):
            raise Exception("No sponsor found for this document, something got unlinked?")
        self.sponsor = self.doc.sponsor

    def completed(self):
        if self.sponsor.autoapprovesigned and self.sponsor.conference.autocontracts:
            if self.sponsor.confirmed:
                send_conference_sponsor_notification(
                    self.sponsor.conference,
                    "Already confirmed sponsor: %s" % self.sponsor.name,
                    "The sponsor\n%s\nhas signed the digital contract. However, the sponsor was already confirmed!\n" % (self.sponsor.name),
                )

            confirm_sponsor(self.sponsor, 'Digital contract')

            if not self.sponsor.invoice and self.sponsor.level.levelcost > 0:
                # Contract signed, time to issue the invoice!
                manager = self.sponsor.managers.all()[0]
                self.sponsor.invoice = create_sponsor_invoice(manager, self.sponsor)
                self.sponsor.invoice.save()
                self.sponsor.save(update_fields=['invoice'])
                wrapper = InvoiceWrapper(self.sponsor.invoice)
                wrapper.email_invoice()

    def expired(self):
        if self.sponsor.autoapprovesigned and self.sponsor.conference.autocontracts:
            if self.sponsor.confirmed:
                send_conference_sponsor_notification(
                    self.sponsor.conference,
                    "Contract expired for already confirmed sponsor: %s" % self.sponsor.name,
                    "The sponsor\n%s\nhas not signed the digital contract before it expired. However, the sponsor was already confirmed!\n" % (self.sponsor.name),
                )
                return

            send_conference_sponsor_notification(
                self.sponsor.conference,
                "Contract expired for sponsor %s" % self.sponsor.name,
                "The sponsor\n%s\nhas not signed the digital contract before it expired. The sponsorship has been rejected and the sponsor instructed to start over if they are still interested.\n" % (self.sponsor.name),
                )
            send_sponsor_manager_email(
                self.sponsor,
                "Sponsorship contract expired",
                'confsponsor/mail/sponsor_digisign_expired.txt',
                {
                    'sponsor': self.sponsor,
                    'conference': self.sponsor.conference,
                },
            )
            self.sponsor.delete()

    def declined(self):
        if self.sponsor.autoapprovesigned and self.sponsor.conference.autocontracts:
            if self.sponsor.confirmed:
                send_conference_sponsor_notification(
                    self.sponsor.conference,
                    "Contract declined for already confirmed sponsor: %s" % self.sponsor.name,
                    "The sponsor\n%s\nhas actively declined to sign the digital contract. However, the sponsor was already confirmed!\n" % (self.sponsor.name),
                )
                return

            send_conference_sponsor_notification(
                self.sponsor.conference,
                "Contract declined for sponsor %s" % self.sponsor.name,
                "The sponsor\n%s\nhas actively declined to sign the digital contract. The sponsorship has been rejected and the sponsor instructed to start over if they are still interested.\n" % (self.sponsor.name),
                )
            send_sponsor_manager_email(
                self.sponsor,
                "Sponsorship contract declined",
                'confsponsor/mail/sponsor_digisign_declined.txt',
                {
                    'sponsor': self.sponsor,
                    'conference': self.sponsor.conference,
                },
            )
            self.sponsor.delete()
