# Generate invoices for discount codes. That is, sponsors that have ordered discount codes,
# that have now either expired or been used fully.
#

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from datetime import timedelta, time

from django.db.models import Q, F, Count

from postgresqleu.confreg.models import DiscountCode
from postgresqleu.confreg.util import send_conference_mail
from postgresqleu.confsponsor.util import send_conference_sponsor_notification, send_sponsor_manager_email
from postgresqleu.invoices.util import InvoiceManager, InvoiceWrapper
from postgresqleu.util.time import today_global


class Command(BaseCommand):
    help = 'Generate invoices for discount codes'

    class ScheduledJob:
        scheduled_times = [time(5, 19), ]
        internal = True

        @classmethod
        def should_run(self):
            return DiscountCode.objects.filter(sponsor__isnull=False, is_invoiced=False).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        # We're always going to process all conferences, since most will not have any
        # open discount codes.
        filt = Q(sponsor__isnull=False, is_invoiced=False) & (Q(validuntil__lte=today_global()) | Q(num_uses__gte=F('maxuses')))
        codes = DiscountCode.objects.annotate(num_uses=Count('registrations')).filter(filt)
        for code in codes:
            # Either the code has expired, or it is fully used by now. Time to generate the invoice. We'll also
            # send an email to the sponsor (and the admins) to inform them of what's happening.
            # The invoice will be a one-off one, we don't need a registered manager for it since the
            # discounts have already been given out.

            if code.count == 0:
                # In case there is not a single user, we just notify the user of this and set it to
                # invoiced in the system so we don't try again.
                code.is_invoiced = True
                code.save()
                send_conference_sponsor_notification(
                    code.conference,
                    "[{0}] Discount code expired".format(code.conference),
                    "Discount code {0} has expired without any uses.".format(code.code),
                )

                send_sponsor_manager_email(
                    code.sponsor,
                    "Discount code {0} expired".format(code.code),
                    'confsponsor/mail/discount_expired.txt',
                    {
                        'code': code,
                        'sponsor': code.sponsor,
                        'conference': code.conference,
                    },
                )
            else:
                # At least one use, so we generate the invoice
                invoicerows = []
                for r in code.registrations.all():
                    if code.discountamount:
                        # Fixed amount discount. Always apply
                        discountvalue = code.discountamount
                    else:
                        # Percentage discount, so we need to calculate it. Ordered discount codes will
                        # only support a registration-only style discount code, so only count it
                        # against that.
                        discountvalue = r.regtype.cost * code.discountpercentage / 100
                    invoicerows.append(['Attendee "{0}"'.format(r.fullname), 1, discountvalue, r.conference.vat_registrations])
                # All invoices are always due immediately
                manager = InvoiceManager()
                code.invoice = manager.create_invoice(
                    code.sponsor_rep,
                    code.sponsor_rep.email,
                    "{0} {1}".format(code.sponsor_rep.first_name, code.sponsor_rep.last_name),
                    '%s\n%s' % (code.sponsor.name, code.sponsor.invoiceaddr),
                    '{0} discount code {1}'.format(code.conference, code.code),
                    timezone.now(),
                    timezone.now() + timedelta(days=1),
                    invoicerows,
                    accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
                    accounting_object=code.conference.accounting_object,
                    paymentmethods=code.conference.paymentmethods.all(),
                )
                code.invoice.save()
                code.is_invoiced = True
                code.save()

                wrapper = InvoiceWrapper(code.invoice)
                wrapper.email_invoice()

                # Now also fire off emails, both to the admins and to all the managers of the sponsor
                # (so they know where the invoice was sent).
                send_conference_sponsor_notification(
                    code.conference,
                    "[{0}] Discount code {1} has been invoiced".format(code.conference, code.code),
                    "The discount code {0} has been closed,\nand an invoice has been sent to {1}.\n\nA total of {2} registrations used this code, and the total amount was {3}.\n".format(
                        code.code,
                        code.sponsor,
                        len(invoicerows),
                        code.invoice.total_amount,
                    ),
                )

                send_sponsor_manager_email(
                    code.sponsor,
                    "Discount code {0} has been invoiced".format(code.code),
                    'confsponsor/mail/discount_invoiced.txt',
                    {
                        'code': code,
                        'conference': code.conference,
                        'sponsor': code.sponsor,
                        'invoice': code.invoice,
                        'invoiceurl': wrapper.invoiceurl,
                        'curr': settings.CURRENCY_ABBREV,
                        'expired_time': code.validuntil < today_global(),
                    },
                )
