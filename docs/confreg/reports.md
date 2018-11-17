# Reports

## Simple reports <a name="simple"></a>

There are a number of simple reports available as direct buttons from
the administration dashboard page.

Some of them are "verification reports", such as finding people who
have not registered or misconfigured sessions. Those reports will have
their button highlighted if they have any data in them.

## Attendee reports <a name="attendee"></a>

Attendee reports allow for the creation of custom reports of almost
anything related to attendees.

For fields, pick the fields you want.

For filters, check boxes for the fields that should be filtered. In
each filter field, type what to filter for. This field can also take
*>* and *<* to indicate that the value should be greater/smaller (for
numbers) or after/before (for dates). For string filters, a *%filter%*
is applied, so it matches partial filters. If a field is marked but
nothing is entered in the search box, the filter will be checked for
presence (meaning not null).

Specify a title if you want one on the report, mainly for printing.

In *Additional columns* specify extra column headers with comma
between them. This is particularly useful if for example generating an
attendee list to tick off people on -- make an empty column for the
tick-mark!

## Time reports <a name="time"></a>

The time reports can be used to draw graphs relative to the time of
conference for a number of things. In particular, they can be used to
compare rates between different instances of conferences.

Time reports are only available to superuser and conference series
administrators. For series administrators, all conferences in the
series will always be available.
