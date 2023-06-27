# Apply or view the diffo f constraints to the configuration
#
# Copyright (C) 2023, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction

import os

from postgresqleu.util.djangomigrations import scan_constraint_differences


class Command(BaseCommand):
    help = 'Dump list of constraints in database'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='Apply the fixes (otherwise, just show)')

    def handle(self, *args, **kwargs):
        path = os.path.abspath(os.path.join(__file__, '../../../migrations'))
        with transaction.atomic():
            scan_constraint_differences(path, kwargs['fix'])
            if kwargs['fix']:
                while True:
                    r = input("Commit transaction? ")
                    if r.lower().startswith('y'):
                        break
                    elif r.lower().startswith('n'):
                        transaction.set_rollback(True)
                        break
