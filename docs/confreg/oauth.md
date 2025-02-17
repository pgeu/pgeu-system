# OAuth

OAuth is currently used for two different things in the system -- for
integrating with [messaging systems](integrations) and for performing
login in case the postgresql.org community authentication system is
not used.

At this point, the authentication part of OAuth is not managed in the
system, only configured manually in the `local_settings.py` file by
setting `ENABLE_OAUTH_LOGIN=True` and setting up the variable `OAUTH`.

## OAuth application registration

OAuth applications are uniquely identified by their base URL. For some
providers these are unique URLs (such as Twitter) whereas other
systems support multiple instances and therefore multiple OAuth
applications (such as Mastodon).

OAuth applications are registered globally in the system, and can be
used my many different accounts in it.

Each OAuth application also has a `Client` and a `Secret`
key. These keys are for *the application*, there will then be a
separate set of keys for each individual account used.

The `Callback URI` / `Redirect URL` / `redirect uri` for OAuth will be
`https://<site>/accounts/login/<provider>/` where `provider` currently
is "twitter" or "mastodon".

### Twitter

The application is created on https://developer.twitter.com/ (logged
in as a Twitter account with a verified phone number -- this does
*not* have to be one of the conference accounts, as it is only
used to manage the actual Twitter application, and not for any
posting). The name of the application does not matter, but it is what
is shown on the posted tweets. The application registration is shared
for the whole instance, across all conference series, and there can
only be one Twitter oauth app per instance.

When creating the application on the twitter developer console, make
sure you:

1. Set up authentication (even if we are not using it). For authentication,
   you *must* pick permissions `Read and write`. Specifically, you
   must *not* include direct messages, or things will break at a later
   stage. You should also not request email from uers. The type of app
   should be set to `Web App, Automated App or Bot` (confidential
   client). The return URL per the top of this page.

1. *After* you have set this up, you must *regenerate* the `Consumer
   Keys`. It's this regenerated key data that should be added to the
   system as `Client` and `Secret`.

1. (in some cases you also have to create generate authentication
   tokens between step 1 and 2 - and if you do create them, you also
   have to regenerate the Consumer Keys)

Due to Twitters limitations on free APIs, webhooks are currently not
supported, as all incoming processing is disabled.

### Mastodon

The Mastodon integration supports multiple different Mastodon
instances, but will default to https://mastodon.social/.

As Mastodon allows dynamic OAuth application, this is simply done by
adding an OAuth Application of type Mastodon with the specified base
URL, and everything else is automatic (just don't forget to hit the
`Save` button).

### LinkedIn

For LinkedIn an application has to be registered at LinkedIn. The
application is created at https://www.linkedin.com/developers/. Note
that on LinkedIn, each app must be "owned" by a page, so a page first
has to be created.

The app must apply for `Community Management API` (which is required
to post to pages). This API requires extra validation by LinkedIn, so
it can take some time to get approved.

The integration only uses the scopes `r_organization_social` and
`w_organization_social`.
