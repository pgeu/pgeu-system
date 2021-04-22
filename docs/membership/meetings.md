# Meetings

The meeting system can manage members-only  and [web
meetings](#webmeetings) and IRC meetings.

IRC meetings require an IRC bot from
https://github.com/mhagander/meetbot to control the IRC channel.

## Meeting

Name
: Name of the meeting, primarily shown on the website

Date and time
: When is the meeting. It will automatically show on the website and
start handing out keys 4 hours before this time.

Open to all members
: Check this box if meeting is available to all active members.

Open to specific members
: Pick individual members who can access the meeting. Only necessary
if *Allmembers* is not checked.

Meeting type
: Specify if this is an IRC meeting (using the bot) or a web meeting (using the
built-in meeting server).

Meeting administrators
: If this is a web meeting, select the member(s) who will be administrators of
the meeting. Does not apply to IRC meetings.

Bot name
: IRC handle of the bot managing the meeting. Does not apply to web meetings.

## Web meetings <a name="webmeetings"></a>

The system comes with a simple built-in web meeting support. This runs
a dedicated server speaking websockets to the browser, where a
lightweight custom javascript client handles the chat itself. The
system knows to handle membership and proxy voting natively, which
makes it a bit cleaner than the IRC meetings in this regard, and has
integrated support for running simple polls where the meeting members
can vote.

In order to use this system, the parameter `MEETING_WS_BASE_URL` must
be set to a websocket URL. Typically this will be
`wss://same.host.as.website/ws/meeting`, and should always use `wss`
(secure web sockets) when used outside of local testing. The meeting
server found in `tools/meetingserver` must be running and responding
on this URL (normally proxied through the web server, but can connect
directly in local testing).

All things said in the meeting is persisted in the PostgreSQL
database, and is thus available for easy building of minutes etc.

### Web meeting states

A web meeting transitions through several stages:

1. Available, not open
: This state opens 2 hours prior to the meeting, and allows all
members to join the meeting, but it's not "official" yet. Members can
join to test connection etc. Messages sent during this stage will be
purged from storage once the meeting is finished.

2. Open
: This state is entered when an admin clicks the *Open meeting*
button. Once the meeting is open, no new members can join. Members who
have previously joined can still re-join (to handle for example a
network outage).

3. Finished
: This state is entered when an admin clicks the *Close meeting*
button. At this point meeting attendees can still chat, but nothing
said goes on the permanent record.

4. Closed
: The meeting transitions to this state when all members have
disconnected while the meeting was in state *Finished*. At this point,
nobody can join anymore.

### Meeting server setup and configuration

The meeting server is separately downloaded from
https://github.com/pgeu/pgeu-meetingserver.

The code builds a standalone binary that can should normally be set up
to run on the same server as the main website. It can also run on a
different server, but it requires direct access to the PostgreSQL
database.

A typical execution of the server is:

```
meetingserver -behindproxy -listen /tmp/.meeting_socket -origin https://my.site -dburl postgres://pgeu@/pgeu?host=/var/run/postgresql
```

This will listen for proxy connections on the Unix socket in
`/tmp/.meeting_socket` (typically proxied from something like nginx),
and decode the `X-Forwarded-For` header in those requests. If nothing
is specified, the server will listen on localhost port `8199` without
looking at proxy servers

The `-origin` parameter should be set to the base name of the
website. This is validated against the `Origin` header in the web
socket request, and has to match exactly for the connection to be
allowed. To disable this check (not recommended in a public install!),
use `-origin *`.

And finally, a connection URL in Go format to access the database has
to be specified.
