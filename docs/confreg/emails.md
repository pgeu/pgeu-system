# Emails

## Attendee emails

Using the *Attendee emails* functionality it is possible to send email
to all attendees, or those of a specific
[registration class](registrations#typesandclasses). Emails sent using
this function will both be sent as an email to the attendee *and*
listed on the registration dashboard for those that have
registered. This means that attendees who sign up *after* the email is
sent will **also** be able to view the emails.

From
:  The *from* address of the email will always be the
[main contact address](super_conference) for the conference.

Regclasses
:  Select the registration classes that the email should be delivered to,
and visible for on the registration dashboard.

Subject
:  The subject of the email

Message
:  The message body. No formatting is done, so make sure you put
reasonable linebreaks in, and don't use markdown.

Emails can (obviously) not be edited after they've been sent.

## Cross conference email <a name="crossconference"></a>

Cross conference emails are currently only available to superusers,
due to the inability to limit sender address.

Cross conference emails are different from attendee emails in that
they are a one-off sending of email. They are not stored server-side
anywhere, and are not viewable in the system after they've been sent
(even for administrators).

Multiple criteria can be set for each email, both including and
excluding. Include criteria are applied first, and then exclude
criteria, so exclude ones take precedence.

First pick the conference, and then either the
[registration class](registrations#typesandclasses) or
[speaker state](callforpaper#states). This can be done for both
include and exclude.

To add multiple either include or exclude filters, click the *+*
button. To remove an existing filter, click the *-* button.

Then fill out the actual email fields:

Senderaddr
:  Email-address used to send the email. Be careful about what is used
here, should always be one where the sending server sets proper DKIM.

Sendername
:  Name of the sender (typically the conference series name, if sent
to a complete conference series).

Subject
:  The subject of the email (!)

Text
:  The body of the email. No formatting is done, so take care with
linebreaks!

Before the email is actually sent a list of recipients will be shown
at the bottom of the form and a confirm box will appear to confirm
sending to all attendees.

All emails will automatically get a footer that says where it was sent
from and that also includes an opt-out link.


### Opt-out <a name="optout"></a>

Each email sent using this functionality will include a link to
opt-out. Opt-out is tracked both at the global (instance) level, and
at the *conference series* level. It is not possible to opt out from a
single conference, but it is possible to opt out either on the full
series or for *all* series.

Note that even if users have opted out from the series, they will
still be sent attendee emails for the conference and any emails
concerning payments.
