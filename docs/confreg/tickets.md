# Tickets and check-in

The tickets and check-in system is optional, but can be useful
especially when working with larger conferences. If enabled, a ticket
will be generated for each attendee, and this ticket should be brought
to the registration at the conference to check in. Whether to make the
actual check-in mandatory is of course up to each conference to
decide, but if check in is not performed there is no need to enable
ticketing.

## Tickets

If nothing else is defined a very basic ticket is generated. In almost
every case, the tickets should be [skinned](skinning) using the
`ticket.json` file.

Tickets will be attached to the conference *welcome email*, and also
be made available for download on the website.

Tickets typically include all the main required information for the
event, as well as a QR code using the attendees identifier token which
can be used by administrators to look them up.

## Queue partitioning

There is basic support for hints around queue partitioning, which can
be enabled if ticketing is enabled. When done, the system will
indicate on the ticket using the first letter of either the first name
or the last name, which queue the attendee should go to for
registration. The reason to put this on the ticket is that it will
then make it clear in the case where the attendee (or check-in
processor) has mixed up first and last names for example.

The theory is that the system will indicate something like "go to
queue for F", without knowing exactly which queues exist. This makes
it possible to define exactly which queues are needed once the amount
of space available for registration desk and number of attendees is
fully known.

### Calculating queue partitions

When queue partitioning is enabled, a report becomes available on the
administrative dashboard to help calculate queue sizes. Simply enter
the desired number of queue partitions, and the system will calculate
(based on current confirmed attendees) which letters to send to which
queue.

## Check-in <a name="checkin"></a>

The check-in system is designed for those working the registration
desk at the event. It's a small web app designed specifically to be
used from mobile (any usability from a desktop browser is purely
accidental).

The system is designed to as quickly as possible find the user
checking in, providing the information needed at the registration desk
(such as t-shirt size and additional options), and then process the
check-in as quickly as possible.

There are multiple ways to access the check-in system. At the base
is a mobile website available from a link on the registration page
of the person performing checkins. There is also a native Android
app available in the
[play store](https://play.google.com/store/apps/details?id=eu.postgresql.android.conferencescanner)
(source available at [pgeu github](https://github.com/pgeu/android-ConferenceScanner).

If a supported mobile device is used (which should include all
reasonably modern android and modern iOS), then the QR code present
on the ticket can be scanned to immediately look up the user. If the
scanning does not work, the attendee does not bring a ticket or the
device is not supported, a regular search-by-text can of course also
be done (which will then search both first and last name,
independently).

Finally, the tokens in the QR codes are valid URLs to the system. If
this URL is visited by somebody who is registered as a check-in
processor, it will be possible to check-in directly from that
URL. Unlike the webapp, this requires the person doing the scanning to
be logged into their account on the mobile device. Any user not being
a check-in processor will just get an access denied error if they scan
the URL. This way of scanning means the general QR scanner
functionality of a mobile phone/browser can be used instead of the
native app, which increases compatibility. In particular iOS devices
can have strange problems with the webapp, in which case this becomes
the preferred way to scan. For Android users, using the native app
referenced above is generally preferred, but both will work.

Once found, the information about the attendee will be shown, and
check-in can be performed. Once the check-in is performed, it's stored
when and by who, so it the same attendee tries to check in again (or a
different one with the same ticket...), it will be clearly shown.

### Scanning fields

Scanning fields allows the check-in process to be split into multiple
steps, where different things are scanned at different times. A
typical use for this is to have conference t-shirts handed out
separately from the main check-in. The permissions are integrated with
the check-in system, so the same people will have permissions on
it. However, instead of scanning the ticket, they will be scanning
attendee badges, to bring up approximately the same information.

The scanning fields are configured as a subset of the
[dynamic properties](reports#dynamic) used in reporting, and for each
scanning field the timestamp when it was stored will be registered in
the dynamic property (and an entry will be written to the registration
log).

### Check-in processors

The people processing the check-ins will get a link on their
registration page that goes to the check-in information page.

This page will contain a link (both directly and as a QR code) to the
check-in app. If multiple scanning fields are used, indepdendent links
will be provided for each of them.

The check-in app itself does *not* require the user to be logged in,
so this link can easily be copy/pasted.

### Check-in testing

The check-in information page referenced above also comes with a test
QR code. This code can be scanned in the check-in app to verify that
the QR scanning part works -- it will just generate a message saying
that the test code has been found, with no side-effects, so it is
fully safe.

### Enabling the check-in app

The check-in app is disabled by default, and needs to be enabled with
a checkbox on the [configuration page](configuring). The app itself
will function even when the system is disabled, but it will be unable
to get or modify any information.

### Check-in and internet connectivity

The check-in process is completely online, so internet must be
working, as well as being able to access the server running the
system. For this reason, it is always advisable to have a paper
backup...
