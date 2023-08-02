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
that exist will be returned. To explicitly search for null fields,
enter the string *\N* (backslash-N). And finally, this field can also take
*>* and *<* to indicate that the value should be greater/smaller (for
numbers) or after/before (for dates).

Once you are done building your filter, click *Query data*. This will
runt he query against your filter, and show you a count of attendees
matching. Once you have done this once, a second form appears, which
allows you to pick some more fields, but you can also update your
filters and re-query the data as needed.

You can specify a title if you want one on the report, mainly for printing.

In *Additional columns* specify extra column headers with comma
between them. This is particularly useful if for example generating an
attendee list to tick off people on -- make an empty column for the
tick-mark!

Finally, click *Generate report*, which will then open the resulting
report in a new tab. Note that this will *not* req-query the database
for new attendees, so if more attendees now match the filter definitions
you made earlier, they will not be included in the report. This is
intentional to make sure the report is predictable.

### Dynamic report fields <a name="dynamic"></a>

For reporting purposes, dynamic fields cna be added to all
registrations for a conference, and then be set as part of report
generatoin. These fields can be used to store persistant data about
the results of reports, and can then be used later on when filtering
new reports.

To use this feature, first declare which fields should be available
for the conference on the [conference](configuring) page. Once this is
done, the fields become available for filtering and for including in
reports. Note that all fields are always stored and treated as text,
and there is no way to store an empty string (storing an empty string
will remove the field, thus it will only match the NULL value using
the `\N` filter).

## Badges

For badge printing, it's often very useful to use the dynamic
properties system, as this will allow "batching" of badges being
generated. This can be built off a generic filter for "all confirmed
but not canceled attendees", with an additional dynamic property for
`badgesprinted` (or pick any name you prefer).

To print this, set the following entries for your filter:

* `Payment confirmed at` (leave the field empty)
* `Canceled at` set to `\N` (to explicitly filter for non-canceled
  registrations)
* `badgesprinted` set to `\N`(to filter for attendees that have not
  yet had the badge printed)

Set `Format` to `Badge`, and press *Generate report*.

Once you have verified that the badges look OK, chose the
`badgesprinted` field and pick a value for it under *Set field*, and
press *Set dynamic field on matching attendees*. It is important that
this is done before a query is re-run, to ensure it has exactly the
same set of attendees as were in the report. You can pick any value
you want to set it to, as the filter is only on "any value exists",
but a good suggestion can be something identifying the batch such as
the date of printing.

You can also generate badges for individual registrations by clicking
the *Preview Badge* button on the registration page, or for multiple
manually selected badges by marking them on the registration list and
generating from there. These are useful for smaller sets of badges,
whereas the report method is more usable for large sets.

## Time reports <a name="time"></a>

The time reports can be used to draw graphs relative to the time of
conference for a number of things. In particular, they can be used to
compare rates between different instances of conferences.

Time reports are only available to superuser and conference series
administrators. For series administrators, all conferences in the
series will always be available.
