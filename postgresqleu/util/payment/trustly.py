from django.conf import settings

from postgresqleu.invoices.models import Invoice

from postgresqleu.trustlypayment.models import TrustlyTransaction, TrustlyLog

from postgresqleu.trustlypayment.util import Trustly
from postgresqleu.trustlypayment.api import TrustlyException


class TrustlyPayment(object):
    description = """
Pay directly using online banking. Currently supported with most banks in {0}.
""".format(', '.join(settings.TRUSTLY_COUNTRIES))

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        i = Invoice.objects.get(pk=invoiceid)
        return '/invoices/trustlypay/{0}/{1}/'.format(invoiceid, i.recipient_secret)

    def payment_fees(self, invoice):
        # For now, we always get our Trustly transactions for free...
        return 0

    def autorefund(self, refund):
        try:
            trans = TrustlyTransaction.objects.get(invoiceid=refund.invoice.id)
        except TrustlyTransaction.DoesNotExist:
            raise Exception("Transaction matching invoice not found")

        t = Trustly()
        try:
            t.refund(trans.orderid, refund.fullamount)
        except TrustlyException as e:
            TrustlyLog(message='Refund API failed: {0}'.format(e), error=True).save()
            return False

        # Will raise exception if something goes wrong
        refund.payment_reference = trans.orderid

        return True

    def used_method_details(self, invoice):
        # Bank transfers don't need any extra information
        return "Trustly"
