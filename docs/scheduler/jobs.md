# Scheduled Jobs

The system provides a built-in job scheduler. All jobs are also
available as external commands through the `manage.py` command in
Django, but using the integrated scheduler makes it easier to set up
and follow up.

The jobs are scheduled on what is hopefully a set of reasonable
defaults in the code. Each job can be configured with an override
schedule if wanted, in which case this will *replace* the built-in
schedule and it will only be run on the override one.

Each job can also be enabled and disabled.

Some jobs are executed in two "phases". The first phase is one or
more queries against the database to figure out if there is anything
for the job to really do. If not, then the job will be skipped, and
rescheduled (this will show up in the "Last skipped" column). Jobs can
be skipped because they have nothing to do (e.g. no point in running
the send refunds job if there are no refunds pending) or if the module
it's working on simply isn't enabled (no point in running the
Braintree synchronization job if there are no Braintree providers
configured).


### Manual running

Using the button on the individual job configuration page, a job will
be scheduled to run immediately. Note that it is just put in the
scheduler queue and will be run by the background process as soon as
possible, so if the background process is either disconnected or
backlogged, the job will not run immediately.

### Holding jobs

During major maintenance, all jobs can be held using the button on the
frontpage. It is of course also possible to just stop the daemon
process that runs jobs.

## Configuring jobs

Each job can be configured with a few parameters:

Enabled
: If the job is enabled to run

Notify on success
: Normally, notification emails are sent to `SCHEDULED_JOBS_EMAIL` for
all jobs that fail. If this checkbox is enabled, notifications will
also be sent for successful jobs, if they generate any output. If they
do not generate any output, no email will be sent. Checking this box
mimics the default functionality of *cron*.

Override times
: If specified, the job will be run on every day at the given
times. Times can be given as a set of comma separated times on the
format HH:MM or HH:MM:SS. Either times or interval can be specified,
not both.

Override interval
: If specified, the job will be run on the specified
interval. Interval is specified in the format MM:SS or
HH:MM:SS. Either times or interval can be specified, not both.


## Installation

First, consider changing the configuration parameter
`SCEDULED_JOBS_EMAIL`. This is the address that will receive all
notifications from the scheduler.

Second, the command `manage.py scheduled_jobs_runner` needs to be
configured in the init system of the server. This should be a service
running with the same privileges as the webapp typically (it should
always be *low* privileges). It should be set to automatically restart
if it fails, typically with a delay of 30 seconds or similar. It
should be configured with a dependency to make sure that PostgreSQL is
started before the job runner.

A template for a `systemd` service file is in `tools/systemd/', but
needs to be adjusted for paths and users before being used.

The daemon will write to stdout and stderr, so care should be taken to
write these to a reasonable logfile unless the init system already
takes care of it (systemd does by default).
