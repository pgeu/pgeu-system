# Integrations

A couple of external systems can be integrated with the conference
system. The following terms are used when setting this system up:

[Messaging Implementation](#implementation)
: This is the "driver" for different types of messaging systems that
  can be configured, for example "Twitter" or "Telegram".

[Messaging Provider](#provider)
: This is a configured instance of an implementation, for example
  "twitter account @xyz" or "mastodon account @abc". Messaging
  providers are created individually for each *conference series*, as
  that is normally what maps to an account. For details of how to
  configure the implementation specific settings, see [Supported
  implementations](#implementation).

[Messaging Configuration](#messaging)
: This is the configuration of which features of a *Messaging Provider*
  that are enabled for a specific conference instance. For some
  providers it may also include more details settings, such as which
  channel to use for sending notifications.

The following features are currently available, supported by different
systems.

* [Social broadcasting](#broadcast)
* [Attendee only broadcasts](#attendeebroadcast)
* [Private notifications](#notifications)
* [Organizer notifications](#orgnotifications)

To start using the system, first set up messaging providers, and then
enable the individual conference messaging features for the
conferences.

If any [messaging configuration](#messaging) is enabled for a
conference that supports wither [Private
notifications](#notifications) or [Attendee only
broadcasts](#attendeebroadcast), attendees will have the option of
connecting their registration with a messaging system in order to
receive notifications.


## Social broadcasting <a name="broadcast"></a>

The social broadcasting integration supports:

* Manually posting to social broadcasting
* Posting conference news
* Posting confirmed sponsorship benefits
* Creating campaigns
* Receiving incoming mentions

### Manually posting to social broadcasting

As an administrator, the easiest way to post to social broadcasting using the
integration is to just add an entry to the table for *Twitter post
queue*. This button becomes available from the main dashboard of a
conference once the integration has been configured.

Only posts which are flagged as *approved* will be posted. All other
posts are queued until they are approved.

The system also comes with a [mobile website](#mobilesite) specifically
to handle moderated postings.

### Posting conference news

Conference news is posted when generated. It will contain just the
title of the news and a link back to the conference website, same as
the RSS system.

Note that this is *separate* from reposting [global news](news#global).

### Posting confirmed sponsorship benefits

For each [sponsorship benefit](sponsors#benefit) it is possible to
define a value for *tweet template*. If included, this will be treated
as a jinja template, and whenever the benefit is confirmed a tweet
will be generated with that template and sent. Normally this is used
for things like "when the logo benefit is confirmed, post a welcome
tweet", but it can be used for any defined benefit.

### Receiving incoming mentions

When a messaging provider is configured to route incoming messages to
a specific conference, they will either be received by webhook or polled
at a regular interval, and added to the incoming queue. If the
[mobile website](#mobilesite) is used, it can be used to track
incoming posts and to either discard or make replies to them.

### Campaigns <a name="campaigns"></a>

Automated campaigns of posts can be created. When a campaign is
created, a number of posts are automatically created and added to the
queue, at a defined interval (including some random portion). The
contents of the tweets are based on data in the database.

All posts are added as not approved, and thus have to be approved
before sending. This also allows the operator to edit the posts and
possibly change some of the text to be more specific.

A full set of jinja operations are available in the campaigns, and
it's possible to do things like define macros, which can make for
fairly advanced templates.

There can be multiple types of campaigns:

#### Approved sessions campaign

This creates a campaign with one post for each approved session in
the system, filtered by which track the session is on. The template is
called with the following variables:

session
: An object referencing this session. It has access to the same
variables as a general template, so it can access for example the
speakers information.

conference
: The current conference object.

#### Sample template

A sample template for this campaign that shows some variables used:

~~~
{%macro speaker(s)%}{{s}}{%if s.twittername%} ({{s.twittername}}){%endif%}{%endmacro%}
Come see {{session.speaker.all()|map("applymacro", "speaker")|join(" and ")}} talk about {{session.title}}

#awesome #conference #pgeu
~~~


### Mobile site <a name="mobilesite"></a>

The mobile website will be enabled for administrators if any
posting is enabled, and for volunteers specifically if the posting
policy allows for volunteers to post. When enabled, a link will show
up on the registration page for these users.

The link itself uses the registration token, which means that it can
be accessed without logging in by somebody who knows the full URL. The
reason for this is to let in particular mobile users store it as a
bookmark in a browser that cannot easily log in. This of course also
means the link has to be treated as secret.

The mobile site will both allow a user to make posts, including
attaching images. On mobile phones the attach image feature will
normally allow images to be taken directly with the camera if wanted,
or an image from the local gallery can be uploaded.

When a post is made it is entered into the posting queue as
unapproved, and will not be posted until it is. Administrators will
have the ability to bypass the moderation step and post directly, but
in the normal workflow should not.

Once a post is queued, it will show up in the moderation
queue. Depending on the posting policy, either an administrator or a
volunteer can approve posts that are in the queue. Once approved, the
scheduled job to post is triggered immediately, so the post will
be sent right away-

The site will also show a list of all pending mentions of the primary
account, and allow the user to either discard them or to reply to
them. This way it's intended that all incoming requests will be
handled one way or another. The same posting policy as new posts
apply, including moderation.

While the page is open, a scheduled job will periodically check if a
new post has shown up in the queue, and post a notification if it has
(provided the user allowed notifications in the browser).

## Attendee only broadcasts <a name="attendeebroadcast"></a>

Attendee only broadcasts are broadcasts that are sent through a system
to all attendees of a conference, but are not posted publicly.

Typical examples of systems for attendee only broadcasts are "telegram
chat channel".

### Notification of upcoming sessions

10-15 minutes before each session, a notification is automatically
generated for a session that's about to start, letting attendees know
which session and in which room.

## Private notifications <a name="notifications"></a>

Private notifications can either be manually sent using "send direct
message" to the attendee from their registration page, and as a way
for parts of the system to generate automatic notifications.

Typical examples of systems for private notifications are "twitter
direct message" or "telegram chat".

### Sending reminders to speaker just before their presentation

If a speaker has registered and connected a messaging system, they will get a
direct message sent between 10 and 15 minutes before their presentation
(depending on cronjob time) reminding them that their presentation
will begin soon, and which room it's in.

## Organizer notifications <a name="orgnotifications"></a>

General notifications that are also sent to the notification email address
will be posted in this channel. Future enhancements may include being able
to interact with such notifications directly, but for now it is a notify-only
channel.

## Setting up

### Messaging Providers <a name="provider"></a>

To create a new messaging provider, press the New button and select
the implementation class.

Depending on which implementation is used, it may be possible to enter
a Base URL for the provider. For example, for Mastodon multiple
different Base URLs can be chosen (for different messaging providers)
in order to support multiple instances of Mastodon, but for Twitter
only one can be chosen (twitter.com).

Once created, the fields should be filled out like:

Internal name
: This name is used when referencing this provider from the backend
interface. This would typically include the name, e.g. "twitter @abc".

Public name
: This is the name used in public interfaces, such as during the
registration process. This would typically be the name of the service,
but for services that can have multiple instances (such as Mastodon),
it makes sense to also include which instance it is.

Active
: If this messaging provider is active.

Route incoming messages to
: If this messaging provider supports receiving incoming messages,
this indicates which conference in the series that incoming messages
should be routed to.

Further fields will be depending on which implementation is used, and
should hopefully be mostly self-explaining.

### Messaging configuration <a name="messaging"></a>

Once the [messaging providers](#provider) have been set up, each
conference gets the ability to configure them.

For simple providers, this just means checking the boxes for which
features of the provider to enable, such as social broadcast or
private notifications.

For providers that support *attendee only broadcasts* or *organisation
notifications*, it will also be possible to configure these specific
channels. The exact details of what is configured and how depends on
the provider.

## Supported implementations <a name="implementation"></a>

The following implementations are currently supported:

### Twitter

The Twitter integration has one Messaging Provider mapping to one
twitter account, thereby giving a conference series it's own twitter
account, but having conferences in it share (by default).

To use the Twitter integration, one must first set up twitter OAuth
credentials. This is done by adding an [OAuth](oauth) application, after
first registering a Twitter application in the Twitter systems.

Once this is done, you can create the Messaging Provider record for
each conference series. Other than the normal fields, there will be a
button to "Initiate login" which will open Twitter in a new window. At
this time, log in with the Twitter account of the conference series,
and authorize the just created app. This will give a PIN code back
which should be copied and pasted into the field on the Messaging
provider configuration.

Finally, you can enable or disable the webhook for this messaging
provider. Webhook is strongly recommended for any use where the server
is publicly available (meaning non-development servers).

On the Messaging Configuration for Twitter providers there is no
configuration to be done other than checkboxes for which services to
enable.


### Telegram

The Telegram integration has one Messaging Provider mapping to one
*bot* in Telegram. This bot must be created manually from a regular
Telegram account, using the telegram *Botfather*.

To create a bot, look up *Botfather* in the global directory and send
a private chat with the text `/newbot`. Give the bot a name
representative of the conference series, and a username that makes
sense under the same rules (and ending in *_bot* per the requirements
of bots). If you want the bot to be able to work in groups (and not just
chats), you need to disable privacy so that the bot can see all messages
posted in the channel.

When you have entered these two the bot is created and the *Botfather*
will give you an access token. Create the Messaging Provider in the
system, and paste the token in the configuration.

As long as the system is installed on a server that's public
(typically everything except developer installs) it's strongly
recommended to use webhooks to communicate with Telegram. Just click
the button to *Enable webhooks* and the system will be fully
configured.


### Mastodon

The Twitter integration has one Messaging Provider mapping to one
Mastodon account, thereby giving a conference series it's own Mastodon
account, but having conferences in it share (by default).

The Mastodon integration supports multiple different Mastodon
instances, but will default to https://mastodon.social/.

To use the Mastodon integration, one must first set up an [OAuth
application](oauth).

Once this is done, you can create the Messaging Provider record for
each conference series. Other than the normal fields, there will be a
button to "Initiate login" which will open Mastodon in a new window. At
this time, log in with the Twitter account of the conference series,
and authorize the just created app. This will give a PIN code back
which should be copied and pasted into the field on the Messaging
provider configuration.

On the Messaging Configuration for Mastodon providers there is no
configuration to be done other than checkboxes for which services to
enable.
