# Emails

## Attendee emails

Using the *Attendee emails* functionality it is possible to send email
to attendees matching a specific criteria (such as a
[registration class](registrations#typesandclasses)), individual
attendees or speakers of sessions (who may or may not later become
attendees).. Emails sent using this function will both be sent as an
email to the attendee *and* optionally listed on the registration
dashboard for those that have registered. This means that attendees
who sign up *after* the email is sent will **also** be able to view
the emails, assuming they are sign up in a way that matches the criteria.

If emails are sent to a recipient that has not yet registered
(typically sent so somebody who has submitted a talk on the call for
papers but not actually registered yet), it will be stored in a queue
and listed under *Pending regs*. As soon as this user (based on user
id) registers it will automatically be transferred to the dashboard of
the user. The email is of course still delivered to the user, just not
connected in the database.

### Sending attendee emails to registrations based on criteria

Sending email to all attendees matching a specific criteria is
done by clicking the *Attendee email* button on the dashboard. Emails
based on criteria are always stored for future attendees matching the
same criteria to see.

From
:  The *from* address of the email will always be the
[main contact address](super_conference) for the conference.

Registration classes
:  Select the registration classes that the email should be delivered to,
and visible for on the registration dashboard.

Attendees with options
:  Select additional options here and the email will be delivered to all confirmed
   attendees that have one of the selected additional options on their registration.

To volunteers
:  Check this box to send to everybody listed as a volunteer at the conference.

To check-in processors
:  Check this box to send to everybody listed as a check-in processor at th conference.

Send at
:  The email will get sent no earlier than this time (defaults to the current time
   which means send right away).

Subject
:  The subject of the email

Message
:  The message body. No formatting is done, so make sure you put
reasonable linebreaks in, and don't use markdown.

A link to the registration dashboard will be automatically included at
the bottom of the email.

Emails can (obviously) not be edited after they've been sent.

Emails sent using this functionality is *not* subject to opt-out
settings, so be careful to only use for active or recent events!

### Sending email to individual attendees

Emails can also be sent to individual attendees, either based on their
registration or based on sessions they have submitted on the call for
papers. If the email is sent based on the session, all speakers of the
session will get a copy of the email.

These emails are initiated from the list view editing *sessions* or
from the list of attendees on the *registration dashboard*. The
rightmost column is used to indicate which recipients to send email to
by clicking the envelope icon, turning it green. Emails will be sent
to all recipients that are marked with green.

Once recipients have been selected, click the *Send email to <n>
attendees* button. This brings up a form with the details:

Send at
:  The email will get sent no earlier than this time (defaults to the current time
   which means send right away).

Subject
:  The subject of the email

Message
:  The message body. No formatting is done, so make sure you put
reasonable linebreaks in, and don't use markdown.

If the email is stored in the database, a link to the registration
dashboard is included at the bottom of the email. If the email is not
stored, a sentence explain that it was sent because of the conference
is added.

Emails can (obviously) not be edited after they've been sent.

Emails sent using this functionality is *not* subject to opt-out
settings, so be careful to only use for active or recent events!

## External email <a name="external"></a>

External emails are emails sent from the conference address(es) to
recipients who are (not yet?) registered for the conference. This
allows sending to arbitrary email addresses, from a selectino of all
the pre-configured addresses on the conference. The sender name will
always be set to the name of the conference.

Since these emails are sent to non-existing attendees, they are not
stored in the system.

## Cross conference email <a name="crossconference"></a>

Cross conference emails are different from attendee emails in that
they are not accessible to attendees after they have been sent. A
record of the email is stored in the database, including all the
recipients, and can be viewed by the administrator for tracing
purposes, but not by the attendee. These emails respect the
opt-out settings, as they are normally used to send email to
"non-current" conferences.

Multiple criteria can be set for each email, both including and
excluding. Include criteria are applied first, and then exclude
criteria, so exclude ones take precedence.

First pick the conference, and then either the
[registration class](registrations#typesandclasses) or
[speaker state](callforpapers#states). This can be done for both
include and exclude.

To add multiple either include or exclude filters, click the *+*
button. To remove an existing filter, click the *-* button.

Then fill out the actual email fields:

Sender address
:  Email-address used to send the email. Be careful about what is used
here, should always be one where the sending server sets proper
DKIM. For non-superusers only addresses registered as either contact
or sponsor address for an existing conference can be used. For
superusers, any address at all can be used, so be careful!

Sender name
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

### Example

Example for sending a CfP reminder to all speakers from previous year(s)
without including speakers who already submitted a talk this year:

* Go to "Send cross conference email"
* Select the previous conference(s) for "Include"
* Select "Speaker: all"
* Select this year's conference for "Exclude"
* Select "Speaker: all"

Fill out all the other details, and send the email.

### Opt-out <a name="optout"></a>

Each email sent using this functionality will include a link to
opt-out. Opt-out is tracked both at the global (instance) level, and
at the *conference series* level. It is not possible to opt out from a
single conference, but it is possible to opt out either on the full
series or for *all* series.

Note that even if users have opted out from the series, they will
still be sent attendee emails for the conference and any emails
concerning payments.
