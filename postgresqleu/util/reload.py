from django.core.management.base import BaseCommand

from django.conf import settings

import os
import sys
import threading

if settings.RELOAD_WATCH_DIRECTORIES:
    import pyinotify
else:
    from django.utils import autoreload


class ReloadCommand(BaseCommand):
    """
    A subclass of BaseCommand that will watch for changes and automatically exit (for reload)
    if something has changed.

    If configured, use a simple inotify check against configured directories and react on all
    changes. If not configured, fall back on the django implementation.

    Subclasses should *NOT* override handle(), instead they should implement handle_with_reload().
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.run_args = None
        self.run_options = None

    def handle(self, *args, **options):
        # Set up our background thread to run the inner handler
        self.run_args = args
        self.run_options = options

        if settings.RELOAD_WATCH_DIRECTORIES:
            wm = pyinotify.WatchManager()

            class EventHandler(pyinotify.ProcessEvent):
                def __init__(self, parent):
                    self.parent = parent
                    super().__init__()

                def process_default(self, event):
                    # We only exit if it's a python or precompiled python change
                    if not event.pathname.endswith('.py') and not event.pathname.endswith('.pyc'):
                        return

                    self.parent.stderr.write("Detected change in {}\n".format(event.pathname))
                    self.parent.stderr.write("Exiting for restart\n")
                    os._exit(0)

            notifier = pyinotify.ThreadedNotifier(wm, EventHandler(self))
            notifier.start()
            for d in settings.RELOAD_WATCH_DIRECTORIES:
                wm.add_watch(d, pyinotify.IN_DELETE | pyinotify.IN_CREATE | pyinotify.IN_MODIFY | pyinotify.IN_ATTRIB, rec=True)

            # Runt he main task on the primary thread
            self._inner_handle()
        else:
            bthread = threading.Thread(target=self._inner_handle)
            bthread.setDaemon(True)
            bthread.start()

            reloader = autoreload.get_reloader()
            while not reloader.should_stop:
                reloader.run(bthread)

            self.stderr.write("Underlying code changed, exiting for a restart\n")
            sys.exit(0)

    def _inner_handle(self):
        self.handle_with_reload(self.run_args, self.run_options)
