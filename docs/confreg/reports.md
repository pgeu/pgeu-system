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

For filtering, different filters can be added by selecting the type of
filter in the dropdown list. The filter will be added to the bottom of
the current list.

Filters are grouped into filterblocks. Within each filter block,
filters are *AND*ed together if there are multiple filters.

The different filterblocks are then *OR*ed with each other to produce
the final results.

When filtering on a text field, a value can be entered to do a
substring search for it. If the field is left empty, it is only
searched for not null/not empty (depending on filter) and any rows
that exist will be returned. And finally, this field can also take
*>* and *<* to indicate that the value should be greater/smaller (for
numbers) or after/before (for dates).

Specify a title if you want one on the report, mainly for printing.

In *Additional columns* specify extra column headers with comma
between them. This is particularly useful if for example generating an
attendee list to tick off people on -- make an empty column for the
tick-mark!

## Badges

Select "Last name", "First name" and "E-mail", and include additional
fields if your badge template uses them.

For badges for all registered attendees you need a filter:

"Payment confirmed" (leave the field empty)

Select "Format: Badge", and generate the report.

## Time reports <a name="time"></a>

The time reports can be used to draw graphs relative to the time of
conference for a number of things. In particular, they can be used to
compare rates between different instances of conferences.

Time reports are only available to superuser and conference series
administrators. For series administrators, all conferences in the
series will always be available.
