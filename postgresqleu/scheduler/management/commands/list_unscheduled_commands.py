#
# List all unscheduled commands
#
# Just regularly running "manage.py" will list all jobs, including the
# scheduled ones. This one makes it easier to find just the ones that
# are intended for manual running.
#

from django.core.management.base import BaseCommand, CommandError
from django.core.management import get_commands, load_command_class

from itertools import groupby


class Command(BaseCommand):
    help = 'List all unscheduled commands'

    def handle(self, *args, **options):
        cmds = [(app, cmd, load_command_class(app, cmd).help)
                for cmd, app
                in get_commands().items()
                if not app.startswith('django') and not hasattr(load_command_class(app, cmd), 'ScheduledJob')]

        for app, g in groupby(sorted(cmds, key=lambda r: r[0]), lambda r: r[0]):
            self.stdout.write("* {}".format(app))
            found = False
            for x, c, h in g:
                self.stdout.write("   {} -- {}".format(c, h))
                found = True
            if found:
                self.stdout.write("")
