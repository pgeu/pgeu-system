# Badges

Other than skinning the website itself, creation of "skinned badges"
is also possible. Unlike the website, if there is no skin created, no
badges can be created (it is of course still possible to download a
CSV list of all registrations and create them separately).

To create badges, use the [Attendee reports](reports#attendee) page.

**Always** create a filter that includes "Payment confirmed". Without
this, badges would be created for attendees who have not paid. The
"Payment confirmed" field will be set automatically even for
registrations that don't need payment, as soon as they are confirmed.

Select output format "badge", and decide if you want borders and/or
page breaks included, depending on printing requirements and the badge
design itself.

It doesn't matter which fields are included, as the badge template
will always have access to all badges.

### Incremental printing

If badges need to be printed incrementally (for example if most badges
have been printed but late registrations have to be printed as a
separate batch), use the date filter functionality on *payment
confirmed*. If the last batch was printed on 2017-10-20 for example,
enter ">2017-10-20" in the filter field.

For easier validation, generate a normal report with this filter
first, and change the output format to *Badges* when ready.
