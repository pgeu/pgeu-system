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

    def upload_tooltip(self):
        return ''


payment_implementations = [
    'postgresqleu.util.payment.dummy.DummyPayment',
    'postgresqleu.util.payment.paypal.Paypal',
    'postgresqleu.util.payment.banktransfer.Banktransfer',
    'postgresqleu.util.payment.adyen.AdyenCreditcard',
    'postgresqleu.util.payment.adyen.AdyenBanktransfer',
    'postgresqleu.util.payment.trustly.TrustlyPayment',
    'postgresqleu.util.payment.braintree.Braintree',
    'postgresqleu.util.payment.transferwise.Transferwise',
    'postgresqleu.util.payment.stripe.Stripe',
    'postgresqleu.util.payment.banktransfer.GenericManagedBankPayment',
]


def payment_implementation_choices():
    return [(x, x.split('.')[-1]) for x in payment_implementations]


def register_payment_implementation(classname):
    if classname not in payment_implementations:
        payment_implementations.append(classname)
