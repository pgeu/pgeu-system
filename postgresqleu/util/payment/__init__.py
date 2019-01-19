from django.conf import settings

from postgresqleu.invoices.models import InvoicePaymentMethod


class BasePayment(object):
    def __init__(self, id, method=None):
        self.id = id
        if method:
            self.method = method
        else:
            self.method = InvoicePaymentMethod.objects.get(pk=id)

    def config(self, param, default=None):
        return self.method.config.get(param, default)


payment_implementations = [
    'postgresqleu.util.payment.dummy.DummyPayment',
    'postgresqleu.util.payment.paypal.Paypal',
    'postgresqleu.util.payment.banktransfer.Banktransfer',
    'postgresqleu.util.payment.adyen.AdyenCreditcard',
    'postgresqleu.util.payment.adyen.AdyenBanktransfer',
    'postgresqleu.util.payment.trustly.TrustlyPayment',
    'postgresqleu.util.payment.braintree.Braintree',
]


payment_implementation_choices = [(x, '.'.join(x.split('.')[-2:])) for x in payment_implementations]
