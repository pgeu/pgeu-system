# Sponsors and sponsorship

### Terms

Sponsorship level
: This corresponds to a specific level of sponsorship such as *Gold*
  or *Silver*

Sponsorship contract
: This represents an uploaded PDF with the terms and conditions for a
  sponsorship level. This can be different between different levels
  for the same conference to make each one shorter, but is typically
  the same.

Sponsorship benefit
:  One sponsorship level can have multiple sponsorship benefits, each
   being something the user sponsor "gets", such as free entry passes
   or logo on website.

Sponsorship benefit class
:  A sponsorship benefit belongs to a class. This defines only how they
   are handled in the system. For example, a specific class handles
   image uploads, and another class handles "click a button".

Claiming a benefit
:  A sponsor *claims* a benefit to indicate they want it. If this is a
   "checkbox claim" then that's all they do. A claim can also require
   input from the sponsor, such as an uploaded image or a specified
   text. What is required or not is controlled by the benefit class.

Declining a benefit
:  By declining a benefit a sponsor can explicitly indicate they do
   not want the benefit.

## Setting up for a conference

To set up sponsorship for a conference, in order:

1. Upload a [sponsorship contract](#contract). Normally just one is
   needed, but if different ones are used then upload them separately.
1. Create one or more [sponsorship levels](#level).
1. Open sponsorship on [the conference](configuring).

Note that the *benefits* should **never** be changed after sponsors
have started to sign up, but there is nothing in the system actually
preventing it (things like fixing spelling and wording is of course
always allowed...)

## Sign-up process

The sign-up process looks slightly different depending on if the
sponsorship level picked requires a signed contract or not.

![Signup process](graphs/sponsorsignup.svg)

In particular, the workflow is 100% automated for sponsors that have
instant signup, and there is nothing that should be done by
administrators other than to click through the approval of the
sponsorship details.

In manual sponsors, the order of processing for the administrators
once the signup is complete becomes:

1. Wait for the signed contract. Countersign and send back.
1. Generate an invoice by going to the sponsorship and click the
   button for it.
1. Optionally, also confirm the sponsorship, unless this is from a
   sponsor known to not pay on time etc. For trusted sponsors, it's
   normal to trust the signed contract and let them proceed, but
   make sure to double check things like invoice details before doing
   so, as reverting from this state is complicated.

## Sponsor waitlist

The sponsor waitlist is managed manually. When a maximum number of
sponsors are set at a level, signup works normally until there are
that many sponsors signed up.

Once that number of sponsors are signed up *and confirmed*, the
sign-up button is automatically removed, and the level cannot be used
anymore.

In the period where there are fewer *confirmed* sponsors than there
are maximum number of allowed sponsors, a wait list is allowed. The
waitlist is *manually* managed, so what happens is that these sponsors
are added as normal, but should not be "clicked through" by the
administrator. Once the limit is exceeded a red warning text is shown
on the page where invoices are generated, to avoid doing this by
mistake.

## Managing sponsors

Once sponsors are confirmed, await them to claim sponsorship
benefits. As soon as benefits are claimed an email is sent to the
sponsor handling address, and administrators are expected to either
confirm or unclaim those benefits "reasonably quickly".

## Changing invoice details

Once a sponsorship invoice has been paid, it can no longer be modified
in any way, like all invoices.

If an invoice has been issued but not paid, it still cannot be
modified, but it can be re-issued. By doing this all the details for
the sponsor remains, including signup dates and benefits. The current
invoice is canceled (and a cancellation notice is sent), and a new
invoice (with a new invoice number) is generated and sent to the
sponsor. The internal connections in the system between the sponsor
record and the invoice record remains.

To re-issue an invoice, start by editing the sponsor details (for
example invoice address or VAT information), and save that. Once this
is modified, press the button to re-issue the invoice, review the
changes and confirm.

## Refunding and canceling

Before a sponsorship is paid, it's easy to cancel -- just cancel the
invoice and the process aborts.

Once a sponsorship is confirmed, the process of cancellation is
coupled to that of refunding, but can be controlled independently.

Refunding is initialized by clicking the refund/cancel button. Refunds
can be either done for the whole sponsorship invoice, parts thereof
(if VAT is enabled, be careful to calculate the VAT amount properly!)
or not at all. Combined with this, the sponsorship can either be
canceled or not.

That means a single sponsorship can be refunded more than once, if
partial refunds are made. This applies as long as the sponsorship is
not canceled -- as soon as it is canceled, further refunds can no
longer be made, and all records concerning the sponsorship are removed
from the system.

## Benefit classes <a name="classes"></a>

The following benefit classes are available:

Require uploaded image
:  This benefit class requires an uploaded image in a specific format
   (typically PNG) and with the configured size and transparency
   settings.

Requires explicit claiming
:  This benefit class requires the sponsor to explicitly claim, but does not
   require any extra information. The benefit can be configured to automatically
   confirm when claimed (for cases where it will always be possible to deliver,
   and you just want to know if the sponsors wants it) or to require manual
   confirmation (default).

Claim entry vouchers
:  This benefit class gives the sponsor the ability to order free attendee
   vouchers of a specified registration type. They do not guarantee
   seats (so they may end up on the waitlist), and they are only
   usable as payment for the entry itself, not for any additional
   options.

Provide text string
:  This benefit class requires the sponsor to submit a specific text,
   within the set minimum and maximum number of words or characters.
   Set either limit to 0 to allow any number.

List of attendee email addresses
:  This benefit class allows the sponsor to download a list of attendee
   email addresses (only those that opted in to sharing) after the
   conference has finished.

Scanning of attendee badges
:  This benefit class allows the sponsor to get access to the webapp
   for scanning attendee badges. Doing so in turn lets them collect
   contact information for those attendees that visit their sponsor
   table and similar, if the badges are scanned. Each attendee also
   gets the ability to refuse sharing data (on the registration form),
   in which case the sponsor will get an error when they try to scan
   their badge.
   Note that for this feature to work, the *Field: badge scanning*
   on the [conference configuration](configuring) must be enabled.

Submit session
:  This benefit class allows the sponsor to submit a session for the
   conference that bypasses the regular call for papers. The class
   will be configured to save to to a specific track, and this is not
   choosable by the sponsor. The benefit will request title and abstract
   for the session as well as name, company, bio and photo for the speaker.
   Once the benefit is confirmed, a distinct speaker profile will be
   created for this speaker, with no connected user account. A session
   entry will be created with the specified information and automatically
   flagged as approved (but not put on the schedule since it has no start
   and end time yet).

## Shipments

A shipment tracking system is built into the sponsorship system. It
can also be used to track shipments unrelated to sponsorships, but in
that case only the administrators can use it.

The system assigns individual shipments unique tracking numbers, using
which it tracks the arrival of the packages. The receiving is handled
outside of the regular system and uses a secure token URL, with the
idea being that this URL can be handed to a venue or a partner to have
them directly update packages as they arrive, if agreed upon.

To use the shipment system, create at least one shipment
address. Until a shipment address is created, the complete system is
disabled.

To generate a shipment address tied to a sponsor, select which
sponsorship levels it should be available to. If no sponsorship level
is selected, the address is only available to the organizers.

A shipment address can be given a start and an end date. These are
only *informational* and not enforced in any way, but they will render
a note to the sponsor about what the first and last dates to have
shipments arrive at this address is.

For each shipment, a full address can be given. As part of this
address, the token `%%` should be inserted at some point, usually at
the end of the first row. This token will be automatically replaced
with the unique number for each individual shipment.

Finally, an address can be given a description which is shown to the
sponsor when they request a shipment.

Each sponsor can request an unlimited number of shipments, each
getting a unique ID. This should be done once for each individually
sent item or trackable item. A single shipment can consist of multiple
parcels, the number of which is entered into the system. Once they
have requested the shipment, they get the ID. When they actually
*send* the shipment, they update the record with the date of the
sending and the parcel count. If available, also tracking information
such as the shipping company and a tracking URL (not required).

The final part of the system is the receiving end. This can either be
handled by interfacing with the recipient (venue, partner, etc)
manually and in that case it's updated by the administrator. Or it can
be handled directly by the recipient, which is the main idea behind
it. The recipient will get a list of all shipments scheduled for that
address, and has the ability to mark them as received as they arrive,
based on the unique number. They can also indicate exactly how many
parcels have arrived (and it is then up to the sender to explicitly
validate this if they want -- the system will show both numbers and a
warning, but does not require the *recipient* to deal with this).

### Emails

Emails are automatically triggered in the system when:

A new shipment is requested
:  An email is generated to the conference sponsorship address

A shipment is marked as sent
:  An email is generated to the conference sponsorship address

A shipment is unmarked as sent
:  An email is generated to the conference sponsorship address

Shipment details are updated *after* it was sent
:  An email is generated to the conference sponsorship address

A shipment is marked as received
:  An email is generated to the *sponsor*, as well as to the
   conference sponsorship address.

A shipment is marked as not received
:  An email is generated to the *sponsor*, as well as to the
   conference sponsorship address.

Number of parcels arrived is changed
:  An email is generated to the *sponsor*, as well as to the
   conference sponsorship address.

## Reference

### Sponsorship <a name="sponsor"></a>

### Sponsorship level <a name="level"></a>

Level name
:  Name of the sponsorship level (shown to the user)

URL name
:  Name-part used in URLs for this sponsorship level (typically a
   slug-style lowercase version of the name)

Cost
:  Price for this level (excluding VAT if VAT is used). If a cost of 0
is entered, no invoice will be generated for this level, and all
confirmation will be handled manually (this is not supported for
levels that are instant buy).

Available for signup
:  Whether this level is currently enabled for signup.

Publicly visible
:  Whether this level is listed on the public website. If a level is
   visible but unavailable it is still listed, just with an indication that
   it's not available. When it's not public, then it's not listed at all.

Maximum number of sponsors
:  Maximum number of sponsors that can sign up at this level. If more
   than this number of *confirmed* sponsors exist, the sign up button
   will be removed. If there are fewer *confirmed* sponsors, but the
   total number including *unconfirmed* sponsors exceed exceed the number,
   sponsors are offered a waitlist. If set to zero then an unlimited
   number of sponsors are allowed at this level.

Instant buy available
:  If this level requires a signed contract. If this box is checked,
   then the sponsor can do a "click-through" accepting of the contract
   and proceed directly to confirmation and invoice, with no explicit
   contract signing required. If it is not checked, then the
   administrator must manually move the sponsorship forward in the
   process once a signed contract is received.

Payment methods for generated invoices
:  Which payment methods will be listed on the generated
   invoices. Typically the instant buy levels support payment by
   creditcard, but higher levels may only support manual bank
   transfers.

Invoice extra description
:  Text that's included as the invoice extra description, which is
   included on the invoice payment page as well as in the email sent
   to the sponsor with the invoice. This can typically be used to
   suggest using specific payment methods, or to inform about special
   terms.

Can buy vouchers
:  Can sponsors at this level buy extra vouchers that they can give to
   employees, customers or others. These vouchers are separate from
   the free vouchers given, and are paid for independently.

Can buy discount codes
:  Can sponsors at this level buy discount codes, which can provide
   either a fixed or percent discount. These discount codes will be
   separately invoiced to the sponsor once they have closed (and it's
   known how much cost they generated).

Benefits
:  A list of [benefits](#benefit) available at this level. New
   benefits can be added with the *Add benefit* button.

### Sponsorship benefit <a name="benefit"></a>

Benefit name
:  Name of the benefit as shown to the sponsor.

Benefit description
:  Free-text description of the benefit as shown to the sponsor.

Sort key
:  Integer indicating the sort order for this benefit, with lower
   numbers sorting first in the list.

Claim prompt
:  A n optional popup prompt that will be shown to the user when
   claiming the benefit.

Autoconfirm
:  Indicates if this benefit should automatically confirm as soon as
   the sponsor has claimed it (checked box) or if it shuld require the
   organisers to explicitly confirm the benefit (unchecked box).

Tweet template
:  A template, in jinja2 format, used to generate tweets when this
benefit is confirmed. If left empty, no tweet is posted. The format
and capabilities of the template is explained under
[campaigns](integrations#campaigns).

Parameters
:  [Benefit class](#classes) specific parameters for this benefit.


### Sponsorship contract <a name="contract"></a>

Contract name
:  Give the contract a name. This is what will be used in selection
   dialogs elsewhere. It will also be used as the name of the PDF when
   sent to end-users.

Contract PDF
:  Upload a PDF with the contract. Take at least some level of care to
   with the size of it. There is no limit enforced by the system other
   than what is configured on the webserver as maximum request size.

Edit field locations
:  Allows editing of the location of fields to add to the contract when
the sponsor downloads it. These fields will be automatically filled with
things like the sponsor name and VAT number, to ensure they match what's
in the registration.

Preview with fields
:  Previews the contract with example sponsor data

Edit digital signage fields
:  Opens an editor to place fields for digital signatures on the contract
using the digial signature provider.

Send test contract
:  Sends a test contract (using the digital signatures provider) to specified
address, to test that the field placements work.

Copy fields from another contract
:  When you have several contracts with the same fields, you can copy the field
definitions from one contract to the other. When doing so, all the fields on the
destination contract will be overwritten and replaced with those from the source
contract. Both static fields and digital signage fields will be copied.
