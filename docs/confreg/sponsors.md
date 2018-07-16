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
administrators.

In manual sponsors, the order of processing for the administrators
once the signup is complete becomes:

1. Wait for the signed contract. Counstersign and send back.
1. Generate an invoice by going to the sponsorship and click the
   button for it.
1. Also confirm the sponsorship, unless this is from a sponsor known
   to not pay on time etc. But for trusted sponsors, it's normal to
   trust the signed contract and let them proceed.

## Managing sponsors

Once sponsors are confirmed, await them to claim sponsorship
benefits. As soon as benefits are claimed an email is sent to the
sponsor handling address, and administrators are expected to either
confirm or unclaim those benefits "reasonably quickly".


## Benefit classes <a name="classes"></a>

The following benefit classes are available:

Require uploaded image
:  This benefit class requires an uploaded image in a specific format
   (typically PNG) and with the configured size and transparency
   settings.

Requires explicit claiming
:  This benefit class requires the sponsor to explicitly claim, but does not
   require any extra information.

Claim entry vouchers
:  This benefit class gives the sponsor the ability to order free attendee
   vouchers of a specified registration type. They do not guarantee
   seats (so they may end up on the waitlist), and they are only
   usable as payment for the entry itself, not for any additional
   options.

Provide text string
:  This benefit class requires the sponsor to submit a specific text,
   within the set minimum and maximum number of words and characters.

List of attendee email addresses
:  This benefit class allows the sponsor to download a list of attendee
   email addresses (only those that opted in to sharing) after the
   conference has finished.

## Reference

### Sponsorship <a name="sponsor"></a>

### Sponsorship level <a name="level"></a>

Levelname
:  Name of the sponsorship level (shown to the user)

Urlname
:  Name-part used in URLs for this sponsorship level (typically a
   slug-style lowercase version of the name)

Levelcost
:  Price for this level (excluding VAT if VAT is used)

Available for signup
:  Whether this level is currently enabled for signup (should normally
   be on unless the level has a maximum number of uses and is sold
   out).

Instant buy available
:  If this level requires a signed contract. If this box is checked,
   then the sponsor can do a "click-through" accepting of the contract
   and proceed directly to invoice. If it is not checked, then the
   administrator must manually move the sponsorship forward in the
   process once a signed contract is received.

Payment methods for generated invoices
:  Which payment methods will be listed on the generated
   invoices. Typically the instant buy levels support payment by
   creditcard, but higher levels may only support manual bank
   transfers.

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

Benefitname
:  Name of the benefit as shown to the sponsor.

Benefitdescription
:  Free-text description of the benefit as shown to the sponsor.

Sortkey
:  Integer indicating the sort order for this benefit, with lower
   numbers sorting first in the list.

Benefit class
:  The [benefit class](classes) for this benefit. If no class is
   specified, the benefit will be automatically claimed when the
   sponsor has signed up.

Claimprompt
:  A n optional popup prompt that will be shown to the user when
   claiming the benefit.

Class parameters
:  [Benefit class](classes) specific parameters for this benefit, in
   JSON format. Will be automatically populated with a default set of
   parameters when created, but their values have to be set.


### Sponsorship contract <a name="contract"></a>

Contract name
:  Give the contract a name. This is what will be used in selection
   dialogs elsewhere. It will also be used as the name of the PDF when
   sent to end-users.

Contract PDF
:  Upload a PDF with the contract. Take at least some level of care to
   with the size of it. There is no limit enforced by the system other
   than what is configured on the webserver as maximum request size.
