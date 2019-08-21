# Integrations

A couple of external systems can be integrated with the system. The following
are currently available:

## Twitter <a name="twitter"></a>

The twitter integration supports:

* Posting conference news
* Posting confirmed sponsorship benefits
* Sending reminders to speaker just before their presentation

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

### Setting up

To set up the twitter integration, first configure `TWITTER_CLIENT`
and `TWITTER_CLIENTSECRET` in the `settings.py` file. These are the
values that can be retrieved after setting up an application on
[apps.twitter.com](https://apps.twitter.com). Note that this application
must be granted permissions to read, write and direct messages.

Once that is done, initiate the integration setup on the website. This
will open a new window to twitter in the browser, where the
application can be authorized (make sure you are logged in with the
*correct* Twitter account at this point!). Once authorized, a PIN code
is shown, which should be copied and pasted into the form on the
original page.
