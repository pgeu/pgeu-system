# Email infrastructure

Email sending is done through a simple *queue* implemented in the
`mailqueue` module.

Any part of the system will insert email into this queue, in a raw
MIME format. A server side cronjob is normally run every minute or
every 2 minutes to push out any emails found in this queue to the
local SMTP server.

There are no attempts to do DKIM or anything similar, as that is all
expected to be handled by the local SMTP server.

To change the local SMTP server that is used to another host and/or
port, configure *settings.SMTPSERVER*. This can be set to for example
*host.domain.com:587* to include both host and port. Note that this
server should be local to make sure it can always receive and queue
outgoing emails, and must not use authentication or other restrictions.

It is explicitly *not* included in the [job scheduler](jobs) to send
emails, as this would make it impossible for that scheduler to
actually send any error reports.
