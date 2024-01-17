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

You can also decide if you want talkvoters to be able to see how others
voted and the overall average vote.  Usually this would be off until
everyone has finished voting.

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

Transfer cost
:  If set to a value it will become possible to create invoices for
transferring registrations. The cost will be per-registration and
independent of registration type.

Notify about registrations
: Send an email to the notification address every time somebody
registers or has their registration canceled.

Send welcome mail
: Should an email be sent to the attendee confirming that they have
completed their registration. For this to be enabled, jinja templating
needs to be enabled, and the contents of the email to be sent should
be stored in `templates/confreg/mail/welcomemail.txt`.

Use tickets
: Enable [tickets](tickets) and check-in. If this is enabled, then for
each user a ticket is generated and attached to the welcome
email. This ticket is built from the `ticket.json` file in the
template directory. Enabling tickets also enables the check-in
tracking system.

Queue partitioning
:  Enable queue partitioning. This will generate information for each
attendee about which queue t stand in based on either first or last
name (pick which one). Information about this partitioning will be
written on the tickets (if included in the templates), so should
normally not be changed after the first tickets have been issued.

Initial common countries
: Initial list of countries to show under *common countries* on the registration
form. Each o these countries will count as one when the list of most
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
: A timestamp (00:00 - 24:00) indicating during which period automated
tweets can be posted. If an automated tweet is queued outside this
window, it will be posted once the window is entered. Manual tweets
can be queued for any time.

Posting policy
: Set the policy fo rusing the [mobile](integrations#mobilesite)
  posting interface.

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

Dynamic properties
:  List of [dynamic properties](reports#dynamic) that can be added
   to each registration. These fields are used for custom reporting
   and similar functions, and are not visible to the end user.

Scanning properties
:  List of dynamic properties that can be used as part of the scanning
   system. For [check-in processors](tickets#scanningfields) this allows
   them to perform secondary scanning of badges to mark other items.
   The list here must be a subset of the *Dynamic properties* above, or
   empty.

Registration open
: If regular registration is open.

Registration open between
: Timestamp to open and close the registration. If these fields are
left empty, the registration is opened and closed based on the checkbox.
If they are specified, the registration will be closed before and
after this range even if the checkbox for open is enabled. Both fields
need ot be satisfied for the registration to be open.

Allow editing registrations
: If a user is allowed to edit an existing registration. Only some
limited fields can be edited, things like t-shirt size and dietary
needs. This is typically turned off once the final list of such
information has to be locked in with a venue, or when badges are
printed (in case some of this information is used on the badges).

Call for papers open
: If the call for papers is open

Call for papers open between
: Timestamp to open and close the call for papers. If these fields are
left empty, call for papers is opened and closed based on the checkbox.
If they are specified, the call for papers will be closed before and
after this range even if the checkbox for open is enabled. Both fields
need ot be satisfied for the call for papers to be open.

Call for sponsors open
: If the call for sponsors is open

Call for sponsors open between
: Timestamp to open and close the call for sponsors. If these fields are
left empty, call for sponsors is opened and closed based on the checkbox.
If they are specified, the call for sponsors will be closed before and
after this range even if the checkbox for open is enabled. Both fields
need ot be satisfied for the call for sponsors to be open.

Schedule publishing active
: If the schedule is published, including times, and rooms.

TBD sessions in schedule
: If sessions in [state](callforpapers) *Pending* should be included
  on the schedule. If they are, their title is replaced with *TBD*,
  and the speaker information is not included.

Session list publishing active
: If the session publishing is active, which just lists the sessions
and their details, typically used before the schedule is done but
talks are being approved. Only tracks which have the "In session list"
flag activated are shown. Change this in "Tracks" for each track.

Cards active
: If the card publishing is active *and* the session publishing is
active, then [cards](skinning#cards) (small adapted images in SVG and
PNG format) will be published for sessions and speakers.

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

Use tags
: Should the [call for papers](callforpapers) ask for tags on all sessions.

Ask for recording consent:
: Should the [call for papers](callforpapers) ask for recording consent
on all sessions.

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

Jinja templates enabled
: Indicate if jinja templating is active for this conference. This can only
  be enabled if the *jinja directory* setting is enabled in the
  [superuser settings](super_conference), but can then be independently
  turned on and off by a non-superuser.

Video link providers
: List of providers that can be used to link to videos (e..g "youtube"
  and "vimeo"). Must be lowercase. Each entry here will create a field
  on the conference sessions (backend only) where information about
  video links can be stored, and later used within the templates.

Width of HTML schedule
: Width in pixels of the built-in HTML schedule. This only controls
the "old style" HTML schedule, which is normally overridden by the
conference templates in which case this has no effect.

Vertical pixels per minute
: Number of pixels to assign to each minute on the Y axis when
generating the "old style" HTML schedule.

