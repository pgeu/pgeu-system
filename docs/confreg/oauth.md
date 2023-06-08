# OAuth

OAuth is currently used for two different things in the system -- for
integrating with [messaging systems](integrations.md) and for performing
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
for the whole instance, across all conference series.

If you wish to use Webhooks for Twitter (recommended for all public
installations when tracking incoming tweets as well as when using it
as a way to deliver notifications, as this gives much better response
times), you must also create a "Dev environment". The free sandbox dev
environment should be enough for most deployments (at the time of this
writing, it supports up to 15 accounts). Again, the name of the
environment does not matter, just attach it to the just created app.

Once all is set up, create the application by copying the
`API key` and `API Secret Key` values from the application
registration as `Client` and `Secret`.

### Mastodon

The Mastodon integration supports multiple different Mastodon
instances, but will default to https://mastodon.social/.

As Mastodon allows dynamic OAuth application, this is simply
done by adding an OAuth Application of type Mastodon with the
specified base URL, and everything else is automatic.
