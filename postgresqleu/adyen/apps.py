from django.apps import AppConfig

from postgresqleu.invoices.signals import invoice_canceled


class AdyenAppConfig(AppConfig):
    name = 'postgresqleu.adyen'

    def ready(self):
        from . import util

        invoice_canceled.connect(util.canceled_invoice_handler)
