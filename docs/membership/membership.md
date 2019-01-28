# Membership

Membership is a simple registry of paying members.

## Configuration <a name="config"></a>

Sender email
: The email address used to send all membership related emails.

Membership years
: The number of years a membership is active for, after payment has completed.

Membership cost
: The cost for *Membership years* worth of membership, in the system base currency.

Country validator
: If enabled, the member must be from a country that fulfills the
requirements of the validator (e.g. must be a European country)

Invoice payment methods
: The available payment methods for paying membership invoices

## Member

Full name
: Full name of the member

Country
: Country the member is from

Listed in the public membership list
: If the member is public or private

Country exception
: If this member is exempt from the [country restrictions](#config)

Member since
: The date the member joined (if the membership expires, this date resets)

Paid until
: How long is the current membership valid until

Expiry warning sent
: If the membership is about to expire, when was the warning last sent?

Log
: A log of all membership events for this member
