from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.conf import settings

import subprocess
import os.path

from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.util.db import exec_to_scalar


def _validate_monitor_request(request):
    if request.META['REMOTE_ADDR'] not in settings.MONITOR_SERVER_IPS:
        raise PermissionDenied("Invalid IP")


@global_login_exempt
def gitinfo(request):
    _validate_monitor_request(request)

    # Get information about our current position in the git structure
    def _run_git(*args, do_check=True):
        p = subprocess.run(
            ['git', ] + list(args),
            stdout=subprocess.PIPE,
            cwd=os.path.abspath(os.path.dirname(__file__)),
            timeout=2,
            check=do_check,
            universal_newlines=True,
        )
        if p.stdout:
            return p.stdout.splitlines()[0]
        return ""

    branch = _run_git('symbolic-ref', '--short', 'HEAD', do_check=False)
    tag = _run_git('tag', '--points-at', 'HEAD')
    commitandtime = _run_git('log', '-1', '--format=%H;%cI')

    return HttpResponse("{};{};{}".format(branch, tag, commitandtime), content_type='text/plain')


@global_login_exempt
def nagios(request):
    _validate_monitor_request(request)

    # Summary view of "a couple of things to monitor", at a global level.
    # Note that this monitoring is about the system *itself*, not about conferences etc.

    errors = []

    # Check that there is a jobs runner connected
    if exec_to_scalar("SELECT NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name='pgeu scheduled job runner' AND datname=current_database())"):
        errors.append('No job scheduler connected to database')

    if exec_to_scalar("SELECT EXISTS (SELECT 1 FROM mailqueue_queuedmail WHERE sendtime < now() - '2 minutes'::interval)"):
        errors.append('Unsent emails are present in the outbound mailqueue')

    if errors:
        return HttpResponse("CRITICAL: {}".format(", ".join(errors)), content_type='text/plain')
    else:
        return HttpResponse("OK", content_type='text/plain')
