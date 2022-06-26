# Schedule

## Scheduling

Once talks have been accepted in the [call for papers](callforpapers),
or sessions have been manually added, scheduling takes place.

The following terms are in use for scheduling:

Rooms
:   This represents a physical room. Two sessions cannot be schedule
in the same room at the same time. A room is not tied to a topic in
any way. A room may or may not be available throughout the
conference. Rooms are typically represented by different columns in
the schedule.

Track
:    A track represents a topic of content. It is *not* tied to a
specific room, so it's perfectly possible to have multiple sessions in
the same track at the same time, as long as they are in different
rooms. Tracks are typically represented by different colors on the schedule.

Session slot
:    A session slot represents a start and an end time on the
schedule. Most sessions are scheduled in a schedule slot, and it's
what the drag-and-drop interface supports doing. However, it is
perfectly valid and possible to manually schedule a session that does
not conform to a schedule slot.

Cross schedule sessions
:     A cross schedule session is one that is not tied to a particular
room, but instead spans across the entire schedule. Typical examples
of this is coffee breaks and lunch. Cross schedule sessions do not show
details about the session.

Tags <a name="tags"></a>
:     Tags can be assigned to each session if enabled at the conference
level. Each session can have zero or more tags assigned. These can later
be used in the schedule for viewing, or similar things. There is currently
not much core functionality like filtering, but could be in the future.

## Building a schedule graphically

Using the "create schedule" functionality a schedule can be built
incrementally using the graphical tools. All approved sessions are
available in a list on the right-hand side, and all rooms and schedule
slots are available on the left.

Cross schedule sessions are typically not scheduled using this tool.

Right-click a session to schedule it, and pick the day, room and
timeslot the session should be. Note that session length is *not*
considered when doing this, so if you assign a session to a different
length slot, it will change length!

To unassign a session, simply right-click the session and choose unassign.

A draft can be saved at any time, and will only be visible to other
administrators.

Once done, click the link at the bottom to publish the schedule. This
operation will show a list of exactly which changes will be
made. Initially this will be a long list, and it's mainly useful when
making changes to the schedule after it has been published. If the
changes look OK, hit the confirm link to publish.

The published schedule will immediately become available *if* schedule
publishing has been activated on the [conference](configuring).

## PDF Schedules

Simple schedules can be built in PDF format, for printing, and usually
gives a much nicer print-out experience than printing the one from the
website.

Schedules can be printed to include only specific [tracks](#tracks),
[rooms](#rooms) or days. Printing can be color, in which case the
tracks are printed in the same color as they would have on the
website, or black and white.

Printing can be done A3 or A4, portrait or landscape. It is also
possible to stretch the schedule out over multiple pages, particularly
useful if for example printing a full day schedule but only having
access to an A4 printer. Print in landscape A4, and tape together to
make for an "almost A3".

## Reference

### Tracks <a name="tracks"></a>

Track name
:	Name of the track

Sort key
:   An integer representing how to sort the track. Lower values sorts
earlier.

Background color
:   Background color to use on schedule (and other places) for this track

Foreground color
:   Foreground color to use on schedule (and other places) for this track

In call for papers
:   Whether this track should be available to choose in the
[call for papers](callforpapers) submission form.

Show company
:   Whether sessions in this track should have the company name of the speaker
	listed on the schedule.

Allow speaker reg
:   Speakers with approved talks in this track will be allowed to
register for free *if* a registration type with one of the
[special registration types](registrations#typesandclasses) for speaker
registration exists.


### Rooms <a name="rooms"></a>

Room name
:   Name of the room

Sortkey
:   An integer representing how to sort the room. Lower values sorts
earlier.

URL
:   A link to more information about the room, such a a link to a map or
in the case of a streamed conference, a link to the stream.

Available days
:   List the days that this room is available. If no day is specified, the
room is made available on all days. If there are no registration days defined
on the conference ,this field does not exist. This field is only used
when building a schedule graphically, not during regular viewing.

Comment
:   An internal comment about this room, typically something like
location and capacity of room. Only used internally, intended for
organizers only.

### Schedule slots <a name="slots"></a>

Start time
:   When this slot starts

End time
:   When this slot ends

### Sessions <a name="sessions"></a>

The form to edit session has the following fields:

Title
:	The title of the session

Speakers
:	One or more speakers. A speaker must have created a speaker
profile before it can be used here, but it the same speaker
profile can be used across multiple conferences.

HTML Icon
:   HTML code to be inserted into schedule (and possibly other places)
representing this session. Can be used to include icons like coffee
mugs for coffee breaks etc. Should be pure HTML.

Status
:	The [state](callforpapers#states) state of this session.

Start time
:	If the session is scheduled, the starting date and time.

End time
:	If the session is scheduled, the ending date and time.

Cross schedule
:	If this session should be displayed across the schedule, instead
of in one room. Typically used for things like breaks and lunch. When
set to cross session, the details for the session cannot be viewed, so
it should not be used for regular sessions.

Track
:	The track selected for this schedule, if any.

Room
:	The room selected for this schedule, if any.

Can feedback
:   Indicates if feedback can be given on this session

Skill level
:   Skill level of this session (if enabled at the conference level)

Tags
:   [Tags](#tags) for this session

Abstract
:   This is the abstract that is listed on the schedule and session
description pages. Any text here is public.

Submission notes
:   These are notes given by the submitter in the call for papers
form, that are only visible to the conference organisers and the
speakers of the session.

Internal notes
:   These are notes that are auto-created by the system, or that are
made by the administrators. These notes are only bisible to the
conference organisers, and *not* to the speakers themselves.

### Speakers <a name="speakers"></a>

Note that speakers are *shared* between all conferences. For each
individual conference, it is possible to edit those speakers that have
submitted one or more sessions for this conference, but not other
conferences.This is, however, not a *security* boundary, as it is
possible to take another speaker and add them to a fake session, and
then edit them. It's more a convenience feature.

The form to edit a speaker has the following fields:

Fullname
:    The full name of the speaker, as shown on the schedule.

Twittername
:    The twitter handle of the speaker, if any.

Company
:    The company of the speaker.

Abstract
:    An abstract for the speaker.

Photo
:    A photo of the speaker, JPEG or PNG format, sized 512x512 pixels. Will
automaticlaly be resized to 512x512 on upload and centered on a transparent
background to keep the aspect ratio, and converted to PNG in order to support
said transparency.


Note that the speaker photo will also be stored in 128x128 format, to support
both thumbnails and legacy templates. This is automatically updated whenever
the main photo field is updated.
