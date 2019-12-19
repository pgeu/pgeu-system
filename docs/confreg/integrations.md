# Integrations

A couple of external systems can be integrated with the system. The following
are currently available:

## Twitter <a name="twitter"></a>

The twitter integration supports:

* Manually posting to conference twitter
* Posting conference news
* Posting confirmed sponsorship benefits
* Creating campaigns
* Sending reminders to speaker just before their presentation
* Polling incoming tweet mentions


### Manually posting to conference twitter

As an administrator, the easiest way to post to twitter using the
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

Note that this is *separate* from reposting global news. Global news
is configured in the settings file.

### Posting confirmed sponsorship benefits

For each [sponsorship benefit](sponsors#benefit) it is possible to
define a value for *tweet template*. If included, this will be treated
as a jinja template, and whenever the benefit is confirmed a tweet
will be generated with that template and sent. Normally this is used
for things like "when the logo benefit is confirmed, post a welcome
tweet", but it can be used for any defined benefit.

### Sending reminders to speaker just before their presentation

If enabled, each speaker that have given their twitter username during
registration (regular registration, not call for papers) will get a
twitter DM sent between 10 and 15 minutes before their presentation
(depending on cronjob time) reminding them that their presentation
will begin soon, and which room it's in.

This of course requires that the speaker follows the conference
account, or that they have public DMs open.

### Polling incoming tweet mentions

When enabled, the system will poll every 5 minutes for mentions of the
configured twitter account, and add it to the queue. If the
[mobile website](#mobilesite) is used, it can be used to track
incoming tweets and to either discard or make replies to them.

## Setting up <a name="twittersetup"></a>

To set up the twitter integration, first configure `TWITTER_CLIENT`
and `TWITTER_CLIENTSECRET` in the `local_settings.py` file. These are the
values that can be retrieved after setting up an application on
[apps.twitter.com](https://apps.twitter.com). Note that this application
must be granted permissions to read, write and direct messages.

Once that is done, initiate the integration setup on the website. This
will open a new window to twitter in the browser, where the
application can be authorized (make sure you are logged in with the
*correct* Twitter account at this point!). Once authorized, a PIN code
is shown, which should be copied and pasted into the form on the
original page.

For each conference a time period start and end can be configured. No
tweets will be posted outside of this time. Any tweets posted during
that time, manual or automatic, will be queued up and sent the next
day once the time period is entered.

Each conference can also be configured with a *posting policy* that
controls how posts from the [mobile site](#mobilesite) are handled.

## Campaigns <a name="campaigns"></a>

Automated campaigns of tweets can be created. When a campaign is
created, a number of tweets are automatically created and added to the
queue, at a defined interval (including some random portion). The
contents of the tweets are based on data in the database.

All tweets are added as not approved, and thus have to be approved
before sending. This also allows the operator to edit the tweets and
possibly change some of the text to be more specific.

A full set of jinja operations are available in the campaigns, and
it's possible to do things like define macros, which can make for
fairly advanced templates.

There can be multiple types of campaigns:

### Approved sessions campaign

This creates a campaign with one tweet for each approved session in
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


## Twitter mobile site <a name="mobilesite"></a>

The mobile website will be enabled for administrators if any twitter
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

When a post is made it is entered into the twitter queue as
unapproved, and will not be posted until it is. Administrators will
have the ability to bypass the moderation step and post directly, but
in the normal workflow should not.

Once a tweet is queued, it will show up in the moderation
queue. Depending on the posting policy, either an administrator or a
volunteer can approve posts that are in the queue. Once approved, the
scheduled job to post tweets is triggered immediately, so the tweet
will be posted right away.

The site will also show a list of all pending mentions of the primary
account, and allow the user to either discard them or to reply to
them. This way it's intended that all incoming requests will be
handled one way or another. The same posting policy as new posts
apply, including moderation.

While the page is open, a scheduled job will periodically check if a
new tweet has shown up in the queue, and post a notification if it has
(provided the user allowed notifications in the browser).
