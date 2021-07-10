# Providing registration data

The registration system can be used to provide information about
registered users to other systems, using a token based API. This way
registrations and payments can be processed in-system, but other
systems can still get information about the users.

The flow for getting the registration data is:

1. The application sends the user to
   `https://site.org/events/conferencename/register/access/?redir=https://some.other.site/`. At this
   point the users login is checked and verified against the
   registration system, and if they are not registered they will get
   an error message indicating so. If the registration is valid for
   the specified conference, the user is redirected back to the URL in
   the `redir` parameter (note! A list of allowed redirect URLs must
   be provided in the [conference configuration](super_conference)). A
   temporary token valid for 5 minutes is generated, and appended to
   the redirection URL with the name `token`.
1. The application intercepts this token, stores it somewhere
   temporarily and redirects the user so the token is removed from the
   URL. This redirect step is strictly speaking optional, but it is
   strongly recommended since the temporary token is single-use.
1. The application then makes a http POST (without redirecting the
   user, using something like XHR) to
   `https://site.org/events/conferencename/register/token/`. The MIME
   type of the POST should be `application/x-www-form-urlencoded`, and
   the contents should be `token=xxx`, where `xxx` represents the
   temporary token received in the previous step. This call must be
   done within 5 minuets before the token expires, and can only be
   made once -- as soon as this call returns, the temporary token is
   removed. The call will return a `JWT` token.
1. The application verifies and uses the contents of the `JWT` token
   as needed.


## Validating the token

Each conference will automatically have a key generated for it, using
which the `JWT` will be signed. The public part of this key can be
downloaded on the URL
`https://site.org/events/conferencename/.well-known/jwks.json`. An
application should always verify the signature of the token before
making any security based decision, but can of course extract things
like the users name without doing so.

The token validity (in the `exp` claim) will be set to a point in time
one day past the end of the conference, so once a token is picked up
for a conference it does not have to be refreshed.

## Token contents

The JWT will look something like this:
```
{
  "iat": 1625332328,
  "exp": 1630367940,
  "iss": "https://site.org/",
  "attendee": {
    "name": "Some Person",
    "email": "someperson@example.net",
    "company": "Some Company",
    "nick": "SomeNick",
    "twittername": "",
    "shareemail": false,
    "regid": 12345,
    "country": "SWEDEN",
    "volunteer": true,
    "admin": true
  }
}
```

Most fields should be self describing.

The value for `regid` is a safe to expose primary key of the
registration. This does *not* identify the user, it identifies the
registration. So if the same user is registered for multiple
conferences, the `regid` will be different between the two and there
is no way through the API to associate them.
