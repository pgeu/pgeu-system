# Signups

Signups are a way to have attendees sign up for specific events, such
as a social event, directly from the registration page. For events
that have attendee limits it supports setting such, as well as a last
time to complete the signup.

### Fields

Author
: The author of the signup. Only visible in the administrative
interface.

Title
: Title of the signup

Intro
: Text describing the signup (basically the contents of the page). Can
use markdown.

Deadline
: Timestamp for the last moment to sign up, or to change the signup.

Maxsignups
: Maximum number of attendees who can sign up.

Options
: A list of comma separated options to show for the signup. If no
options are given, the options "Yes" and "No" will be shown. This is
typically used for e.g. a dinner invitation and then with options
"Yes", "Yes with a plus one" and "No".

Optionvalues
: By default, whatever is picked as an option counts the same, and the
summary will show a count for each value. If a set of values is
entered in this field, the number of values must be exactly the same
as the number of options. If this is done, the results are still shown
tabulated per option but there is *also* a total count shown where the
values are weighed. This can for example be used in the dinner example
above by assigning the weights "1,2,0" in which case the total value
will then represent the total number of people going.

Public
: If checked, this signup is available to all *registered*
attendees. A public signup cannot track "Awaiting response".

Visible
: If checked, then any attendee who has permissions on the signup
(through it being public, or explicitly listed) can also see who else
signed up.

Available to registration types
: For non-public signups, attendees of these registration types can
sign up.

Available to attendees
: For non-public signups, these specific attendees (in addition to
those of the permitted registration types) can sign up

## Sending email

Using the send email functionality, it is possible to send an email to
attendees for a signup. This is a one-time email that goes to the attendees
email and is optionally stored on their registration page.

For each email a subject and a body can be specified (no formatting is
done, so make sure to put reasonable linebreaks in place, and don't
use markdown).

The recipients can be picked to be a combination of the different
answers given, or whether a response has been given at all.

It is also possible to speficy *all*. This only makes sense when the
signup isn't public, as it will send the message to all current users
on the signup but not future ones, but the permissions will apply to
future ones. In this case, it' sbetter to send a regular attendee
email.

The emails will be sent from the main conference
[contact address](super_conference).

## Results

The results will have a summary with how many attendees have picked
each specific option, as well as the total value calculated from
weighted values. Below it there will also be a complete list of every
individual response.

## Editing attendee signups

Normally, the attendees should handle their own signups, and they
should never be edited.

However, it is sometimes required that the administrator edit them,
for example if the deadline has passed, and an attendee needs to
change their response.

All responses that have been recorded can be edited. In a signup that
only has yes/no as the answer, the no responses are not recorded, so
changing a record to no will remove it. For both types of signups it
is always possible to remove an entry.

If the signup is *not public*, it is also possible to add a new
response (for example if an attendee never signed up, but reported
their attendance via email or phone or other means). Duplicate
responses are of course not allowed.
