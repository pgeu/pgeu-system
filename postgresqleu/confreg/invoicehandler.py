from django.conf import settings

from postgresqleu.mailqueue.util import send_template_mail, send_simple_mail
from .models import ConferenceRegistration, BulkPayment, PendingAdditionalOrder
from .models import RegistrationWaitlistHistory, PrepaidVoucher
from .util import notify_reg_confirmed, expire_additional_options

from datetime import datetime


class InvoiceProcessor(object):
    # Process invoices once they're getting paid
    #
    # In the case of conference registration, this means that we
    # flag the conference registration as confirmed.
    #
    # Since we lock the registration when the invoice is generated,
    # we don't actually need to verify that nothing has changed.
    #
    # All modifications are already wrapped in a django transaction
    def process_invoice_payment(self, invoice):
        # The processorid field contains our registration id
        try:
            reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            raise Exception("Could not find conference registration %s" % invoice.processorid)

        if reg.payconfirmedat:
            raise Exception("Registration already paid")

        reg.payconfirmedat = datetime.now()
        reg.payconfirmedby = "Invoice paid"
        reg.save()
        notify_reg_confirmed(reg)

    # Process an invoice being canceled. This means we need to unlink
    # it from the registration. We don't actually remove the registration,
    # but it will automatically become "unlocked" for further edits.
    def process_invoice_cancellation(self, invoice):
        try:
            reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            raise Exception("Could not find conference registration %s" % invoice.processorid)

        if reg.payconfirmedat:
            raise Exception("Registration already paid")

        # Unlink this invoice from the registration. This will automatically
        # "unlock" the registration
        reg.invoice = None
        reg.save()

        # If this registration holds any additional options that are about to expire, release
        # them for others to use at this point. (This will send an additional email to the
        # attendee automatically)
        expire_additional_options(reg)

        # If the registration was on the waitlist, put it back in the
        # queue.
        if hasattr(reg, 'registrationwaitlistentry'):
            wl = reg.registrationwaitlistentry
            RegistrationWaitlistHistory(waitlist=wl,
                                        text="Invoice was cancelled, moving back to waitlist").save()
            wl.offeredon = None
            wl.offerexpires = None
            wl.enteredon = datetime.now()
            wl.save()

        # If the registration was attached to a discount code, remove it so that it is no
        # longer counted against it. Also clear out the field, in case others want to use
        # that discount code.
        if reg.discountcode_set.exists():
            reg.discountcode_set.clear()
            reg.save()
        if reg.vouchercode:
            reg.vouchercode = ''
            reg.save()

    # Return the user to a page showing what happened as a result
    # of their payment. In our case, we just return the user directly
    # to the registration page.
    def get_return_url(self, invoice):
        # The processorid field contains our registration id
        try:
            reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            raise Exception("Could not find conference registration %s" % invoice.processorid)
        return "%s/events/%s/register/" % (settings.SITEBASE, reg.conference.urlname)

    # Admin access to the registration
    def get_admin_url(self, invoice):
        try:
            reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            return None
        return "/events/admin/{0}/regdashboard/list/{1}/".format(reg.conference.urlname, reg.pk)


class BulkInvoiceProcessor(object):
    # Process invoices once they're getting paid
    #
    # In the case of conference bulk registrations, this means that we
    # flag all the related conference registrations as confirmed.
    #
    # Since we lock the registration when the invoice is generated,
    # we don't actually need to verify that nothing has changed.
    #
    # All modifications are already wrapped in a django transaction
    def process_invoice_payment(self, invoice):
        # The processorid field contains our bulkpayment id
        try:
            bp = BulkPayment.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            raise Exception("Could not find bulk payment %s" % invoice.processorid)

        if bp.paidat:
            raise Exception("Bulk payment already paid")

        bp.paidat = datetime.today()

        # Confirm all related ones
        for r in bp.conferenceregistration_set.all():
            r.payconfirmedat = datetime.now()
            r.payconfirmedby = "Bulk paid"
            r.save()
            notify_reg_confirmed(r)

        bp.save()

    # Process an invoice being canceled. This means we need to unlink
    # it from the registration. We don't actually remove the registration,
    # but it will automatically become "unlocked" for further edits.
    def process_invoice_cancellation(self, invoice):
        try:
            bp = BulkPayment.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            raise Exception("Could not find bulk payment %s" % invoice.processor)
        if bp.paidat:
            raise Exception("Bulk registration already paid")

        # Unlink this bulk payment from all registrations. This will
        # automatically unlock the registrations. Also notify the
        # attendees that this happened.
        for r in bp.conferenceregistration_set.all():
            r.bulkpayment = None
            r.save()

            if r.attendee:
                # Only notify if this attendee actually knows about the
                # registration.
                send_template_mail(bp.conference.contactaddr,
                                   r.email,
                                   "Your registration for {0} bulk payment canceled".format(bp.conference.conferencename),
                                   'confreg/mail/bulkpay_canceled.txt',
                                   {
                                       'conference': bp.conference,
                                       'reg': r,
                                       'bulk': bp,
                                   },
                                   sendername=bp.conference.conferencename,
                                   receivername=r.fullname,
                )

            # If this registration holds any additional options that are about to expire, release
            # them for others to use at this point. (This will send an additional email to the
            # attendee automatically)
            expire_additional_options(r)

            # If the registration was attached to a discount code, remove it so that it is no
            # longer counted against it. Also clear out the field, in case others want to use
            # that discount code.
            if r.discountcode_set.exists():
                r.discountcode_set.clear()
                r.save()
            if r.vouchercode:
                # Also mark the voucher code as not used anymore
                vc = PrepaidVoucher.objects.get(vouchervalue=r.vouchercode)
                vc.usedate = None
                vc.user = None
                vc.save()

                r.vouchercode = ''
                r.save()

        # Now actually *remove* the bulk payment record completely,
        # since it no longer contains anything interesting.
        bp.delete()

    # Return the user to a page showing what happened as a result
    # of their payment. In our case, we just return the user directly
    # to the bulk payment page.
    def get_return_url(self, invoice):
        try:
            bp = BulkPayment.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            raise Exception("Could not find bulk payment %s" % invoice.processor)
        return "%s/events/%s/bulkpay/%s/" % (settings.SITEBASE, bp.conference.urlname, invoice.processorid)

    # Admin access to the bulk payment we just send to the dashboard
    def get_admin_url(self, invoice):
        try:
            bp = BulkPayment.objects.get(pk=invoice.processorid)
        except ConferenceRegistration.DoesNotExist:
            return None
        return "/events/admin/{0}/regdashboard/".format(bp.conference.urlname)


class AddonInvoiceProcessor(object):
    can_refund = False
    # Process invoices for additional options added to an existing
    # registration.
    #
    # Since we lock the registration when the invoice is generated,
    # we don't actually need to verify that nothing has changed.
    #
    # All modifications are already wrapped in a django transaction

    def process_invoice_payment(self, invoice):
        try:
            order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
        except PendingAdditionalOrder.DoesNotExist:
            raise Exception("Could not find additional options order %s!" % invoice.processorid)

        if order.payconfirmedat:
            raise Exception("Additional options already paid")

        order.payconfirmedat = datetime.now()
        if order.newregtype:
            order.reg.regtype = order.newregtype

        for o in order.options.all():
            order.reg.additionaloptions.add(o)

        order.reg.save()
        order.save()

    def process_invoice_cancellation(self, invoice):
        try:
            order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
        except PendingAdditionalOrder.DoesNotExist:
            raise Exception("Could not find additional options order %s!" % invoice.processorid)

        # We just remove the entry completely, as there is no "unlocking"
        # here.
        order.delete()

    # Return the user to their dashboard
    def get_return_url(self, invoice):
        try:
            order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
        except PendingAdditionalOrder.DoesNotExist:
            raise Exception("Could not find additional options order %s!" % invoice.processorid)

        return "%s/events/%s/register/" % (settings.SITEBASE, order.reg.conference.urlname)

    # Admin access to the registration
    def get_admin_url(self, invoice):
        try:
            order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
        except PendingAdditionalOrder.DoesNotExist:
            return None
        return "/events/admin/{0}/regdashboard/list/{1}/".format(order.reg.conference.urlname, order.reg.pk)
