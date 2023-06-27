# Dump the list of constraints in the db, for later diffing
#
# Copyright (C) 2023, PostgreSQL Europe
#
from django.core.management.base import BaseCommand

import os

from postgresqleu.util.djangomigrations import dump_expected_files


class Command(BaseCommand):
    help = 'Dump list of constraints in database'

    def handle(self, *args, **kwargs):
        path = os.path.abspath(os.path.join(__file__, '../../../migrations'))
        dump_expected_files(path)
        print("Expected constraints dumped in {}".format(path))
