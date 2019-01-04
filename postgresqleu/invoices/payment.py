# The PaymentMethodWrapper needs to be in it's own file, so we don't
# create a circular dependency between models and util.
from django.utils.safestring import mark_safe


class PaymentMethodWrapper(object):
    def __init__(self, method, invoice, returnurl=None):
        self.method = method

        self.invoice = invoice
        self.invoicestr = invoice.invoicestr
        self.invoiceamount = invoice.total_amount
        self.invoiceid = invoice.pk

        self.returnurl = returnurl

        try:
            pieces = method.classname.split('.')
            modname = '.'.join(pieces[:-1])
            classname = pieces[-1]
            mod = __import__(modname, fromlist=[classname, ])
            self.implementation = getattr(mod, classname)()
            self.ok = True
        except Exception:
            self.ok = False

    @property
    def name(self):
        return self.method.name

    @property
    def description(self):
        return mark_safe(self.implementation.description)

    @property
    def available(self):
        # If not specifically set, it means the method is always available. If it has the ability
        # to control availability, call into it.
        if hasattr(self.implementation, 'available'):
            return self.implementation.available(self.invoice)
        else:
            return True

    @property
    def unavailable_reason(self):
        if hasattr(self.implementation, 'available'):
            return self.implementation.unavailable_reason(self.invoice)
        else:
            return None

    @property
    def paymenturl(self):
        try:
            return self.implementation.build_payment_url(self.invoicestr, self.invoiceamount, self.invoiceid, self.returnurl)
        except Exception as ex:
            print ex

    @property
    def payment_fees(self):
        if hasattr(self, 'implementation') and hasattr(self.implementation, 'payment_fees'):
            return self.implementation.payment_fees(self.invoice)
        else:
            return "unknown"

    @property
    def can_autorefund(self):
        return hasattr(self, 'implementation') and hasattr(self.implementation, 'autorefund')

    @property
    def used_method_details(self):
        if hasattr(self, 'implementation') and hasattr(self.implementation, 'used_method_details'):
            return self.implementation.used_method_details(self.invoice)

    def autorefund(self, refund):
        if hasattr(self, 'implementation'):
            if hasattr(self.implementation, 'autorefund'):
                return self.implementation.autorefund(refund)
            else:
                raise Exception("No support for autorefund in method {0}".format(self.method))
        else:
            raise Exception("No implementation found for method {0}".format(self.method))
