from django.apps import AppConfig


class ConfsponsorAppConfig(AppConfig):
    name = 'postgresqleu.confsponsor'

    def ready(self):
        from postgresqleu.digisign.util import register_digisign_handler
        from postgresqleu.confsponsor.invoicehandler import SponsorDigisignHandler, SponsorAdditionalDigisignHandler

        register_digisign_handler('confsponsor', SponsorDigisignHandler)
        register_digisign_handler('confsponsoradditional', SponsorAdditionalDigisignHandler)
