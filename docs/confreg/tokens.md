# Access tokens

Access tokens are created tokens that enable "secret URLs" with access
to specific information from the conference.

This can for example be live-pulling data into a Google spreadsheet,
or consuming it from a JavaScript based schedule webpage, or any
other interesting ideas people can come up with.

The idea between the specific access token objects is that each
individual service that uses this should be given a separate
token. This way it becomes possible to revoke a token for just one
such consumer without shutting down all the others.

### Reference

The access token objects have the following fields:

Token
:  This is the secret URL token. It's automatically filled with random
data when a new token is created, and it cannot be changed.

Description
:  Internal description. This is not used by the system anywhere, it's
just for administrators to know what is what.

Permissions
:  This list the different kinds of access that can be retrieved using
this token. For each access type it will also have a csv (comma
separated) and tsv (tab separated) values link that includes the
token. (More formats may be added in the future).

