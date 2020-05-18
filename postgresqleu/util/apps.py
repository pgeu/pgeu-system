from django.apps import AppConfig, apps
from django.contrib import admin
from django.db.models.signals import post_migrate
from django.db import transaction

import logging
import types

from postgresqleu.util.forms import ConcurrentProtectedModelForm

from .auth import PERMISSION_GROUPS
from .oauthapps import connect_oauth_signals


#
# When all migraitons have run, ensure that all the currently
# in use permissions group actually exists.
#
def handle_post_migrate(sender, **kwargs):
    # Ensure all permissions groups exist
    # (yes, we have a hardcoded list..)
    with transaction.atomic():
        Group = apps.get_model('auth', 'Group')
        for g in PERMISSION_GROUPS:
            g, created = Group.objects.get_or_create(name=g)
            if created:
                print("Created access group {0}".format(g))


#
# Inject the ConcurrentProjectedModelForm into all ModelAdmins that don't
# explicitly specify override it. Do this by patching out the meaning
# of admin.ModelAdmin to be our own form which inherits from it.
#
class ConcurrentInjectedAdmin(admin.ModelAdmin):
    form = ConcurrentProtectedModelForm


class UtilAppConfig(AppConfig):
    name = 'postgresqleu.util'

    def ready(self):
        connect_oauth_signals()

        post_migrate.connect(handle_post_migrate, sender=self)

        # Override the default ModelAdmin in django to add our validation fields
        admin.ModelAdmin = ConcurrentInjectedAdmin

        self._oldreg = admin.site.register
        admin.site.register = types.MethodType(self._concurrent_injected_register, admin.AdminSite)

        # Now check for optional modules, and log if they are not available
        try:
            import cairosvg
        except ImportError:
            logging.getLogger(__name__).warning("Could not load cairosvg library, PNG cards will not be available")

        try:
            import qrencode
        except ImportError:
            logging.getLogger(__name__).warning("Could not load qrencode library. QR code based functionality will not be available")

    #
    # Define our own handling of registering a model for admin without
    # it's own class. The default is to set admin_class to ModelAdmin
    # in that case, so we just do it one step early in order to use our
    # own injected model from above.
    #

    def _concurrent_injected_register(self, self2, model_or_iterable, admin_class=None, **options):
        if admin_class is None:
            admin_class = ConcurrentInjectedAdmin
        return self._oldreg(model_or_iterable, admin_class, **options)
