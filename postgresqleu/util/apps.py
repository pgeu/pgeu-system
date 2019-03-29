from django.apps import AppConfig, apps
from django.db.models.signals import post_migrate
from django.db import transaction

from .auth import PERMISSION_GROUPS


def handle_post_migrate(sender, **kwargs):
    # Ensure all permissions groups exist
    # (yes, we have a hardcoded list..)
    with transaction.atomic():
        Group = apps.get_model('auth', 'Group')
        for g in PERMISSION_GROUPS:
            g, created = Group.objects.get_or_create(name=g)
            if created:
                print("Created access group {0}".format(g))


class UtilAppConfig(AppConfig):
    name = 'postgresqleu.util'

    def ready(self):
        post_migrate.connect(handle_post_migrate, sender=self)
