# Configuring a conference

This documentation page covers how to configure an existing
conference. For information about how a superuser can create a
completely new conference, see the [separate page](super_conference#new).

### Base configuring

There are a few base configuration steps to always perform.

Set the maximum number of attendees before the [waitlist](waitlist)
activates. This should always be set to a few below venue capacity, to
make sure a multireg doesn't "break the bank".

Configure the automatic cancellation of invoices that are old past a
certain time. As the conference approaches, this number should be
decreased. The risk of keeping it too high is that people create an
invoice, which then "blocks" a seat at the conference, without paying
it. During that time, it's unknown if they will actually attend, so
seats cannot be given to others.

Once the autocancel time is decreased below a certain threshold, some
payment methods that don't complete immediately (notably things like
IBAN bank transfers) will automatically become unavailable to the attendees.


Decide if you want a welcome email to be sent to all attendees when
their registration is fully completed (payment confirmed), which is
normally recommended. If you do, of course also set the text of that
email. The email will be sent from the address configured as the
contact address by the [superuser](super_conference).

If needed, add a text added as a prefix before the
[additional options](registrations) listing on the registration form.

### Registration fields

Configure which additional fields should be included on the
registration form, such as Twitter name or Dietary needs (see
[below](#conferenceform) for reference). This should always be done
before the first registration is allowed, to make sure the same data
exists on all attendees.

### Workflow steps

You can separately enable each of the different user workflow steps
for [registration](registrations), [call for papers](callforpapers),
[call for sponsors](sponsors), [schedule](schedule) and
[feedback](feedback). Make sure you don't enable any steps until the
organisation is ready for it.

### Call for papers

Decide if you want skill level prompts in the
[call for papers](callforpapers) and visible in the
[schedule](schedule), and set the intro text used on the
[call for papers](callforpapers).

### Roles

There are four types of roles that can be configured at the level of
conference.

Testers are users that can bypass the restrictions on which parts of
the workflow are open, e.g. they can perform a registration even if
registrations are closed. The idea is that this can be used for
example to test skinning functions, and to validate the setup of
things like [registration types](registrations).

Talkvoters are users that can vote on talks in the
[call for papers](callforpapers).

Staff are users who are allowed to [register](registrations) with a
registration that requires staff (basically intended for free or
discounted registrations). This is assigned to users *before* they
register, to gain access to this registration type.

Volunteers are *registered* users who can participate in the
[volunteer schedule](volunteers). Note that this requires the users to
actually be registered for the conference in order to be
selected. This is a separate flag instead of a registration type so
that it's easy to for example have attendees who are both speakers and
on the volunteer schedule. If volunteers should get free entry as
well, that is typically handled either with a
[registration type](registrations) that requires manual validation, or
with a custom [voucher or discount code](vouchers).

The final role that exists in a conference is an administrator. This
can only be assigned by a [superuser](super_conference).

## Reference

### Conference details <a name="conferenceform"></a>

The form to edit a conference has the following fields:

Attendees before waitlist
: Number of confirmed attendees before the [waitlist](waitlist) is
activated. This should be below the venue maximum *with some margin*,
as the number of attendees can "jump" with either multi-registrations
or parallel registration processes by multiple users.

Autocancel invoices
: Invoices are automatically canceled if not paid after this many
hours. Should always be set to ensure there are no "dangling invoices"
from people who are not completing their registration, making it
impossible to know if they will use their seat or not. Typically
starts out as a high value that is decreased as either the conference
draws closer or it starts approaching sold out.

Notify about registrations
: Send an email to the notification address every time somebody
registers or has their registration canceled.

Send welcome mail
: Should an email be sent to the attendee confirming that they have
completed their registration.

Welcome email contents
: Contents of said welcome email

Use tickets
: Enable [tickets](tickets) and check-in. If this is enabled, then for
each user a ticket is generated and attached to the welcome
email. This ticket is built from the `ticket.json` file in the
template directory. Enabling tickets also enables the check-in
tracking system.

Queue partitioning
:  Enable queue partitioning. This will generate information for each
attendee about which queue t stand in based on either first or last
name (pick wihch one). Information about this partitioning will be
written on the tickets (if included in the templates), so should
normally not be changed after the first tickets have been issued.

Initial common countries
: Initial list of countries to show under *common countries* on the registration
form. Each o these counttries will count as one when the list of most
common countries is populated. Once registrations start arriving, they
will get replaced by actual countries used as they show up.

Promotion active
: Should this conference be listed in promotional parts of the website.
Without this, the only way to access the conference information is to
know the URL for it.

Promotion text
: Short text (supports markdown) with information about the conference,
which is use din promotional pages on the main website.

URL to promo picture
: An URL pointing to a picture promoting this event, which will be
used on the main website. If left blank a default (or random)
picture will be used. Picture must have an aspect ratio of 2.3, but
will otherwise be reasonably sized to fit the screen of the visitors.

Don't post tweet before/after
: A timestamp (00:00 - 24:00) indicating during which period tweets
can be posted. If a tweet is queued outside this window, it will be
posted once the window is entered.

Field t-shirt
: Should the field asking for t-shirt size be displayed on
registration form. Only used if t-shirts are given out.

Field dietary
: Should the field asking for dietary needs be displayed on the
registration form. Only used if catering is provided.

Field nick
: Should the field asking for nickname be displayed on the
registration form.

Field twitter name
: Should the field asking for twitter name be displayed on the
registration form.

Field badge scanning
: Should the field asking to allow sponsors to scan the attendees
badge be displayed on the registration form.

Field share email
: Should the field asking to share email address with sponsors be
displayed on the registration form.

Field photo consent
: Should the field asking the attendee to give (or not) consent to
have their photograph taken at the event.

Additional intro
: Text shown on the registration page just above the list of
additional options. Typically introduces what the additional options
are. Can contain markdown.

Registration open
: If regular registration is open.

Allow editing registrations
: If a user is allowed to edit an existing registration. Only some
limited fields can be edited, things like t-shirt size and dietary
needs. This is typically turned off once the final list of such
information has to be locked in with a venue, or when badges are
printed (in case some of this information is used on the badges).

Call for papers open
: If the call for papers is open

Call for sponsors open
: If the call for sponsors is open

Schedule publishing active
: If the schedule is published, including times, and rooms.

Session list publishing active
: If the session publishing is active, which just lists the sessions
and their details, typically used before the schedule is done but
talks are being approved.

Check-in active
: If the [check-in](tickets) system is active and attendees can be
checked in.

Conference feedback open
: If registered attendees of the conference can leave
[feedback](feedback) on the full conference.

Session feedback open
: If registered attendees of the conference can leave
[feedback](feedback) on individual sessions.

Skill levels
: Should the [call for papers](callforpapers) ask for skill levels on
all sessions, and should they be displayed on the schedule and session
lists.

Call for papers intro
: Text shown on the [call for papers](callforpapers) page, above the
actual call for papers. Can contain HTML.

Testers
: List of users who are assigned as testers of the conference. These
users can bypass the restrictions above and make registrations and
submissions even when they are closed, etc. This can be both
registered users and not registered users.

Talkvoters
: List of users who can vote in the
[call for papers](callforpapers). This can be both registered users
and not registered users.

Staff
: List of users who can register as staff using the special
[registration type](registrations). This is typically users who have
not registered when they are added, since they will later use the
staff registration to become registered.

Volunteers
: List of registered users who participate in the
[volunteer schedule](volunteers). This must be registered users.

Check-in processors
: List of registered users who work with [checking in users](tickets)
on arrival. This must be registered users.

Width of HTML schedule
: Width in pixels of the built-in HTML schedule. This only controls
the "old style" HTML schedule, which is normally overridden by the
conference templates in which case this has no effect.

Vertical pixels per minute
: Number of pixels to assign to each minute on the Y axis when
generating the "old style" HTML schedule.

