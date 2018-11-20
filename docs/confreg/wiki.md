# Wiki pages

The registration system comes with a very simple wiki system for
editing pages. It comes with a permissions system that makes it
possible to use this system to publish text pages that are supposed to
be viewable only by attendees (by restricting who can edit the page),
or act as a "true wiki" to let attendees edit the pages. No pages can
ever be viewed by users who are not confirmed attendees of the conference.

Attendees can never create new pages, they must always be created by
an administrator. But once created, attendees can edit them, if
permissions allow.

In the admin interface, the following fields can be set:

url
: This is the URL name of the page, *not* the complete URL. It can
only contain alpha-numerical, underscore and dash. Unlike many other
wikis, this is *not* derived from the page title.

Title
: This is the title of the page, used in page listings and in the
title of the page itself. Can contain (almost) any characters.

Author
: Each page has an author that is the *registration* of the creator of
the page. This is never shown to attendees, only administrator
(however, mind that any *editing* of the page will show up).

Contents
: The initial contents of the page. Markdown is supported. Note that
pages should normally *not* be edited here once they have been
created, because that will edit the last revision *without* creating a
new revision! Instead, edit the pages through the user interface,
reached from the link *regular editor* above the form.

Public view
: If all *registered* attendees can view this page (fully public to
non-registered attendees not supported).

Public edit
: If all *registered* attendees can edit this page. Permission to edit
implies permission to view.

History
: If attendees that have permissions to view the page (through it
being public or through explicit permissions) can view the history of
changes on the page, including who made them and the viewing of a
diff.

Viewer registration types
: Registrations types that can view this page (if it is not public),
for example if a page should be restricted to speakers.

Editor registration types
: Registration types that can *edit* this page (if it is not
public). Permission to edit implies permission to view.

Viewer attendees
: Specific attendees that can view this page (if it is not public
*and* they are not registered using a registration type that provides
access)

Editor attendees
: Specific attendees that can *edit* this page. Permission to edit
implies permission to view.

## Wiki page subscriptions

From the user interface, it is possible to *subscribe* to a wiki
page. If this is done, the attendee will get an email on any changes
made in the *user interface*. Changes made through the admin interface
do *not* trigger emails.

## Wiki page notifications

New wiki pages and edits *in the backend system* will generate an
email to the conference contact address (but not to regular attendees,
subscribed or not).
