# Invoices & Payments

All payments in the system are centered around the concept of
invoices. No payments are processed outside of invoices.

An invoice can be manually created, in which case nothing special
happens once it's paid. It can also be attached to an Invoice
Processor, which is then activated upon payment. Separate portions of
the system like conference registration, sponsorship or membership,
each have their own Invoice Processor. The Invoice Processor is
independent of how the invoice is handled.

If enabled, all invoices generate automatic [accounting](accounting)
records as they are completed. No accounting entries are done at
invoice issuing, only at completion.

## Flagging invoices as paid

Invoices paid to an unmanaged bank account, or otherwise confirmed to
be in the system but not handled by the automated methods, can be
flagged as paid using the invoice administration system. In this case,
the administrator is assumed to have validated all details.

## Managed bank accounts

Managed bank account is a special case of the available payment
methods. This is an account where the system can somehow get a list of
transactions as they happen, including details about the transaction.

When transactions occur on a managed bank account get they get fed
into the central processing. This processing knows how to match some
of them, and if they don't match, will provide an interface for doing
manual matching.

For some managed bank accounts, these transactions are automatically
loaded through a job running in the [schedule jobs runner](jobs). For
others the transactions are manually uploaded, but automatically
processed.

When at least one managed bank account supports file uploading (and
is configured and active), a button will show up on the admin
dashboard for *Bank file uploads*. Under this page a list of all
uploaded files can be viewed, and new uploads can be made. Hover the
mouse pointer over the button for uploading files to get instructions
for how to download the correct format file from the specific bank
provider.

### Managed bank accounts and invoices

If the invoice payment reference (as calculated and printed on the
invoice payment page) is found *and* the amount on the invoice
matches, the invoice in question will automatically be flagged as paid
and the transaction will *not* show up in the pending bank transaction
system.

### Managed bank accounts and payouts

If a different payment method (or any other part of the system where
this would make sense) knows about a payout happening to a managed
bank account, it can register this information in the system. It does
so by creating a Pending Matcher, which is a combination of a regular
expression and an amount. It will in this case also leave an open
accounting entry. When a transaction shows up on this managed bank
account with the correct amount and a transaction text that matches
the regexp, the accounting entry will be automatically closed and the
transaction will *not* show up in the pending bank transaction system.

### Manually handling bank transactions

Any bank transaction not matching the above will be listed on the page
for managing pending bank transactions. These will have to be handled
manually. There are three main options for handling them:

Match payment to invoice
:  This can be done if the automatic matcher does not work, but it is
*known* which invoice it is. This can be done in case of a missing
payment reference but the rest of the details are clear enough for
example. It can also be done if the amount of the payment is not
correct -- in this case, the difference of amount will be recorded on
a payment fees account. If the difference is very small (similar to
other payment fees) it may be easier to just match the payment and
accept the difference as a cost, rather than dealing with
sub-payments.

Match payment to multiple invoices
:  This can be used in case a single payment contains the payments
for multiple invoices, when somebody has "helpfully" merged two
payments. This *only* works if there amounts match exactly and there
are no fees involved.

Match payment to matcher
:  This can be used as a workaround for incorrect bank matchers.
Normally, when a transaction that matches a bank matcher shows up,
it automatically gets processed. In case the transaction text has
changed or is incomplete, the matcher might not work. In this case,
it can be matched manually. Only exact amount matches can be processed
this way.

Create open accounting record
:  This will simply create an open accounting record for this
transaction (on the correct account), and direct the user to the
accounting system to fill out the detail. This is the normal path for
transactions that are not related to invoice payments.

Discard
:  The transaction can be discarded completely if it's known to be
handled manually elsewhere (for example if a manual accounting record
was already created).

## Payment methods

A number of different automated payment methods can be supported
simultaneously in the system. This is made up of Invoice Payment
Methods, which are instances of Payment Method Implementations.

Each Invoice Payment Method has an internal name which is used in all
the administration pages, and a Name which is used in all public
facing one. For example, there can me multiple different methods
called Credit Card in the public system, but having different names in
administration in order to differentiate them (which makes sense as
long as not more than one is enabled for any given invoice).

Individual parts of the system, like conference registration and
membership can select which payment methods can be used for this
particular system. For example, some methods are more or less
appropriate for costs that are high and low.

The following fields can be configured on all payment methods:

Name
:  The name of the payment method used externally

Internal name
:  The name of the payment method used in administration pages

Active
:  Whether this method can be used. Since an invoice method that has
at some point been used cannot be deleted (due to foreign keys), it
should instead be Disabled if it should not be used.

Sort key
:  Value representing how to sort this method when multiple ones are
showed.

Implementation class
:  Reference to the underlying implementation class for this payment
method. Cannot be changed, only viewed.

### Payment implementations

The following payment implementations are available

#### Dummy payment

This method is only used for testing. All payments will be approved by
the user just clicking a button. Will only function if DEBUG is
enabled in the installation.

#### BankTransfer

This is a simple manual bank transfer, with no automation. It is
configured with a django template that will get rendered to show a
static page to the person paying the invoice, which should contain all
the bank details. All processing is handled completely manually.

#### Paypal <a name="paypal"></a>

This method allows the payment using either a Paypal account or a
Creditcard.

Once connected to a Paypal account it will download and manage all
transactions on this account. This means that if the account is also
used for other things, those transactions will be imported and
generate warnings about not matching.

To set up the paypal connection, a Paypal app registration must be done.
To do this, go to `developer.paypal.com`, and create a *REST API
app*. Record the *client id* and *secret* and copy these to the
configuration form. Under *App feature options*, make sure the app has
*Accept payments* (default) and *Transaction search* (*not* enabled by
default), and remove all other permissions, including the options
under *Advanced* (under Accept payments). Repeat this configuration
for *both* the sandbox *and* the live environment, but note that there
are different keys.

It also requires a Return URL to be configured in Paypal. Once the method
has been created, information about this will be visible at the bottom
of the configuration page. The return URL configuration on the REST app is
currently *not* used.

#### Adyen Creditcard

This method is for Creditcard payments using Adyen. This is a fairly
complex setup, but very capable. It uses a mix of direct validation,
notifications, and downloaded reports to track all the stages of a
payment. It's particularly suitable if a fairly large number of
transactions are expected.

The system is using Adyens "Hosted Payment Pages" service, which means
that all the actual processing happens at Adyen, thus not requiring a
PCI certified installation.

There are numerous steps to configure it. Much of the details needs to
be set up according to the Adyen manuals. The integration points are
all documented on the form itself.

#### Adyen Banktransfer

This is a special version of the Adyen processing. It requires there
to be a master setup using Adyen Creditcard (though it doesn't have to
be used), and it always uses the same Adyen Merchant Account as that
one. The Creditcard provider will specifically identify the IBAN
transfers as they arrive and route them to this processor.

It's set up as a separate processor due to the slowness of IBAN, and
will disable itself 5 days ahead of an invoice expiring. This is to
make it less likely that an invoice is canceled while the asynchronous
payment is being processed.

Note that with this payment method, the IBAN number and payment
details, including the reference number, is handled entirely by
Adyen. There is no way to view them from the administration side, or
the Adyen backend, and new ones are generated if one returns to the
payment page.

#### Braintree Creditcard

This method uses the Braintree creditcard gateway. Unlike the Adyen
system, this is a semi-hosted system, where the payment interface is
loaded though javascript from the Braintree systems, but the page
itself hosted as part of the system.

This module requires the Python module `braintree` to be installed.

#### Stripe Creditcard

This method uses the Stripe creditcard system. This uses the Stripe
"Checkout" system, which uses a mix of server-side code and hosted
javascript, with the actual payment form entirely hosted by Stripe.

#### Trustly Banktransfer

This method uses the Trustly system for online bank
payments. Basically it allows for payments from a regular bank
account, logged in using internet banking, without most of the
downsides of IBAN transfer. The amount is guaranteed to be correct,
and most payments complete within seconds. It is, however, limited in
which banks are supported.

As PostgreSQL Europe has a deal with Trustly that processes all
payments without fees, there is currently no support for fees in the
system. If somebody without such a deal wants to use the provider,
this should be added.

#### TransferWise

This is a managed bank transfer method using the TransferWise
system. Unlike many other banks, TransferWise provides a simple to use
REST API to fetch and initiate transactions.

Transactions are fetched on a regular basis by a scheduled job. These
transactions are then matched in the same way as any other
transactions.

If the API token used to talk to TransferWise has *Full Access*, it
will also be possible to issue refunds. If it only has Read Only
access, payments can still be processed, but refunds will not work.

Refunds also require that the sending bank included the IBAN
information required to issue a transfer back. This information may or
may not be included depending on sending bank, but the system will
automatically validate this information when the transaction is
received, and if the required information is not present, the refund
function will not be available.

If refunds are enabled, automatic payouts can also be enabled. In this
case, the balance of the account is monitored and once it goes above a
certain limit, an IBAN transfer to a different bank account is
generated. The payment will be made leaving a defined amount of money
still in the account to handle things like refunds.

## Currencies

The system can only support one currency, globally, at any given
time. This is specified in the `local_settings.py` file, and should
normally never be changed. If it's changed once there is data in the
system, things will break.
