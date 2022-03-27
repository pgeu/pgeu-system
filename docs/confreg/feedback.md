# Feedback

The feedback systems consists of [session feedback](#session) and
[conference feedback](#conference). They can be independently enabled
in the [configuration](configuring), and some events will only use
some of them.

## Session feedback <a name="session"></a>

When enabled, feedback is collected on each session. A fixed set of
fields are collected for each session -- rankings from 1-5 on topic
importance, content quality, speaker knowledge and speaker
quality. Other than this it also collects a set of free text comments
that are visible only to the organisers, and a set of free text
comments that are visible only to the speaker.

Feedback is enabled for an individual session once the start time for
the session has passed. That way the list of sessions with feedback
available becomes incrementally available as the conference goes on.

Each speaker can view their own feedback through the call for papers
page.

Administrators can view the collected feedback across all sessions on
the admin page.

### Toplists

On the administrators page to view feedback there are also toplists
with the highest scoring talks and speakers in each category. Be
careful with the information on these lists, particularly in sharing
it, so that people understand what it means. In particular, if there
are multiple speakers on a talk, they share the score for both talk
*and* speaker, which can give very surprising results if the same
speaker also has their own talk.

## Conference feedback <a name="conference"></a>

The conference feedback contains one set of questions that is answered
once by each (potential) attendee. The set of questions is dynamic and
are created by entering a number of *feedback questions*. For each
question, the following fields are available:

Question
:  The actual question

Text field
:  If the response to the question is textual. If this box is not
checked, the question will be a rating from 1-5.

Text choices
: If the response is freetext per above, this field can contain a set
of options separated by semicolons. If it does, the form will contain
a list of options. If the field is freetext and has nothing in the
textchoices field, a regular textbox is used.

Sort key
:  An integer representing the sort order of this field. Lower numbers
sort earlier.

Start new fieldset
:  If specified, this question will create a new fieldset (section) on
the form, and the string in this field will be used as the title. If
left empty, this field will belong to the same fieldset as the
previous (per sortkey) field.
