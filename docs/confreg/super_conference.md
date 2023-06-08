# Editing superuser parameters

This documentation page covers how to edit the superuser only parameters
for a conference, including [creating a new conference](#new). For
information about how to edit the regular parameters for a conference, see
the [separate page](configuring.md).

## Creating a new conference

To create a new conference, select the *Create new conference* button
on the conference administration homepage. This is only available to
superuser, since it allows referencing things like local paths on the
server.

Fill out all the fields as you normally would when editing the
conference, per the [reference](#conferenceform).

Note that an accounting object will be automatically created for a new
conference with the same name as the conference urlname, if it does
not already exist. This can be changed later by editing the conference
if necessary. This accounting object is set to *active* by default.

If the conference is held in a VAT jurisdiction that has never been
used before, the VAT rates have to be registered in the accounting
system *before* the new conference is created, and picked on
creation. This can be delayed (by picking no VAT), but it's very
important that it's properly configured before the first invoices are
generated.

## Reference

### Superuser conference form <a name="conferenceform"></a>

The form to edit superuser parameters has the following fields:

Conference name
:  The display name of the conference. Can change without invalidating
any data.

URL name
:  The name used to form the url of the conference. As this field is also
used to key urls and a number of other things, it is **strongly recommended**
to never change this for a conference once it's been set up.

Series
:  The conference series this conference belongs to

Start date
:  The start date of the conference

End date
:  The end date of the conference

Location
:  The physical location (e.g. City, Country) of the conference

Time zone
:  The time zone this conference is held in.

Contact address
:  Email address to contact the conference organisers on. This address is
also used to send emails from. The server with the system installed on should
preferably have DKIM set up for this domain.

Sponsor address
:  Email address to contact conference organisers on about sponsorship. This
address is also used to send emails from. The server with the system installed on
should preferably have DKIM set up for this domain.

Notification address
: Email address that notifications are sent to and from. This is
internal notifications such as when registrations are happening. It is
*not* used as the sender of any emails going to outside addresses.

Conference URL
:  URL to the conference homepage

Administrators
:  The people who should have full administrative permissions on this conference.
Those people can then use the regular conference configuration form to set all
other parameters for the conference.

Jinja directory
:  The directory where the Jinja templates for the conference are located on
the server, if any. If no Jinja directory is specified, all conference pages will
be rendered in the default templates. If an invalid directory is specified, all
conference pages will generate an error.

Accounting object
:  The accounting object that should be assigned to all invoices for this conference

VAT rate for registrations
:  The VAT rate (if any) to apply to all invoices for registrations

VAT rate for sponsorship
:  The VAT rate (if any) to apply to all invoices for sponsorship

Invoice payment options
:  The payment options available for invoices for registrations and
addons to this conference. This does not include sponsorship invoices,
but it does include the invoices that sponsors will get if they for
example buy extra vouchers.

Signing provider
:   The provider to use for digital signatures of sponsorship contrats. Leave empty
to use manual contracts only.

Contract sender name
:   The name to use as the sender of digital contracts

Contract sender email
:   The email address to use as the sender of digital contracts

Contract expiry time
:   Number of days before a contract expires with the signing provider, if the
provider supports it.

Manual contracts
:   Allow manual contract signing by downloading and signing a PDF. This must be
enabled if there is no digital signature provider. If there is a digital signature
provider, turning on manual contracts as well allows the sponsors to choose how they
want to sign the contracts.

Automated contract workflow
:   Enable automatic workflow for digital signatures. This means that once a
contract is signed, the sponsorship is automatically enabled and an invoice is created
and sent. If disabled, that step has to be done manually.

Allowed web origins for API calls
:  A list of allowed web origins for making [API calls](regprovider.md).
This will be used both for validating a redirect URL and for
controlling what must be in the Origin header when making an API
call to get the JWT token.
