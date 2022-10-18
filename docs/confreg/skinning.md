# Conference skinning

By default all conference pages are rendered in the standard
template. There is, however, the ability to override certain things,
which is configured by fields in the conference model.

The proper way to do this in the current version is to use the
`jinja2` based method, as this will also allow for automatic
deployment of static pages for the conference (if wanted).

To utilize this system, for each conference to be skinned, create a
directory structure like:

    /templates
      /pages
      /confreg
    /static


In the `/static` directory, place any static files (and subdirectories)
to be included in a static site deploy. If no static site deploy will
be done, this directory can be ignored and won't be used.

In `/templates`, place a file called [base.html](#basetemplate). All
the conference templates will inherit from this file, so without it,
all urls will return 404.

If the static webpage system is used, templates can be added under the
`/templates/pages` directory. Each file will be rendered using `jinja2`
into an output file called `index.html` in a directory named by the
template. So for example, `/templates/pages/about.html` will render into
`about/index.html` in the resulting static directory. The only exception
to this is `index.html`, which will be rendered as `index.html` without a
subdirectory.


## Base template <a name="basetemplate"></a>

In the base template, the entire HTML structure should be defined. The
skin can do anything it wants with HTML, css and javascript. Note that
some pages rely on JQuery being present, so it should always be included.

The following blocks should be defined in the base template:

title
: This block gets the page title. Normally just defined as the
  contents of the &lt;title&gt; tag. By default it should contain a generic
  title, such as the name of the conference.

extrahead
: This block must be declared inside &lt;head&gt;, so the other templates
  can insert e.g. css. By default it should be empty.

pagescript
: This block must be declared either inside the &lt;head&gt; or the &lt;body&gt;,
  but must be *after* jquery is loaded. This is where the pages will
  insert local javascript. By default it should be empty.

content
: This block gets the main content of the page. It should be declared
  inside whatever container elements are used. By default it should be
  empty.

You can of course also declare any other blocks you want.

## Variables

When rendering the main conference pages, the following variables are
always available:

pgeu_hosted
: Always set to True, so it can be used to detect how the page was
  rendered.

conference
: Contains the conference object for the current conference

pagemagic
: Contains a magic value indicating which part of the site this page
  renders for. The values can be

    reg
:     Registration form and related pages

    schedule
:     Schedule and related pages

    sessions
:     Session list and related pages

    feedback
:     Feedback and related pages

    cfp
:     Call for papers and related pages

    news
:     News related pages

username
: Contains the current logged in users username

githash
: Contains the hash of the current git head for the active
  checkout. This can be used for cache-busting URLs. If git is not
  used, this will of course be empty.

csrf_input
: If a form, this will contain the django CSRF input field

csrf_token
: If a form, this will contain the django CSRF token

Additional variables may be available on individual pages, but
normally that's handled by the builtin templates.


## Additional variables

If additional variables need to be used, they can be defined in a file
called `context.json` in the templates directory. The contents of this
hash will be added to all requests, both when deployed as static and
when run under the main conference system.

## Overriding variables

For the static deployment process, any number of override context
files can be created in the `context.override.d` directory. Any files in this
directory named `*.json` will be loaded (in alphabetical order), overriding
any values coming from `context.json`.

These files are typically used to for example override the git hash (by
specifying "githash":"" in the json data) to turn off cache busting on
local test deployments, or to override base locations for links etc.

These files are normally not committed to the git repository, as it would
in that case apply to the main static checkout.


## Overriding templates

Normally, it's enough to use the base template and then let the
upstream templates render what's in the *content* block. But in some
cases it might be necessary to take control over the complete
template. When doing that, it's important to remember that the
variables passed to the template might change at some point in the
future, at which point the template has to be updated.

To override a template, simply put a HTML file in the
`/templates/confreg/` directory - for example
`/templates/confreg/schedule.html`.

When testing template overriding it might be necessary to push a
template to the production server and test it there. To do that, add a
`.test` to the end of the filename (e.g. `schedule.html.test`) and then
access the URL with `?test=1`.

# Static building

If static pages are used, the script `deploystatic.py` can be used to
create a directory that can be served up as a static website, either
locally or on a server. Note that this command doesn't actually serve
anything, it just creates the directory. A simple way to serve up a
directory for testing is to just run


    python -m SimpleHTTPServe 9000

(9000 being the port number), which will serve up the current
directory.

The syntax is:

    deploystatic.py <sourcepath> <destpath>

Where &lt;sourcepath&gt; should point at the root directory as described in
the first section of this page. The contents of the `/static/`
subdirectory will be copied directly into the &lt;destpath&gt; directory,
and for each file in `/templates/pages/`, standard `jinja2` template
processing will be applied and the output written to a subdirectory of
the &lt;destpath&gt; directory (see the same section for structure).

Care is taken to only update files that have actually changed.

The recommendation is to copy the `deploystatic.py` script from the
latest version of the upstream repository rather than include it in
the conference website repository, to make sure that it's the same
version that's used on the central server that's being used.

Any files present in the destination directory but not generated by
`deploystatic.py` will automatically be removed at the end of the run,
making sure the output is in sync with the contents of the source.

## Static sources

`deploystatic.py` can deploy from a working directory, or directly from
a git branch using the `--branch` parameter. This is primarily indented
for automated deployments from git hooks.

## Static deployment maps

If a file called `.deploystaticmap` exists in the `/templates/pages`
directory, this file will be used to control which files are deployed
instead of deploying all files. The full contents of the `/static/`
directory is always deployed, but this allows the control of which
pages are. The file format is a series of source:destination pairs
separated by colons. For example, a file with:

    home.html:
    other.html:testing

Will deploy the contents of `/templates/pages/home.html` into the root
of the destination directory and called `index.html`, and the contents
of `/templates/pages/other.html` will be deployed into `other/index.html`
in the destination directory.

# Cards <a name="cards"></a>

Cards are (small?) images published in SVG and PNG format that can be
referenced for example to generate automatic images when links are
posted to Twitter or other social networks. Cards are generated for
speakers and sessions.

To access the card for, just append `/card.svg` or `/card.png` to the
URL of the session or speaker.

Cards are rendered using the `confreg/cards/*.svg` templates in the
skin. `PNG` format cards are generated by first rendering the `SVG`
format card and then converting it to PNG.

The different types of cards available are:

speaker.svg
: Generate a card for each speaker

session.svg
: Generate a card for each session

Unlike some other templates, the included SVG templates in the default
system are *not* meant to be used for anything other than an
example. They should always be overridden, and until that is done, card
publishing should not be
[enabled on the conference](configuring#conferenceform).

# Tickets and Badges <a name="badges"></a>

Tickets and badges can be generated in PDF format based
on the templates. This is done in two stages - first a `jinja2` template
is applied to a source JSON file, generating a complete JSON
definition of the badge. Then this JSON is parsed and turned into an
actual PDF format.

To use the PDF generation system, create one or more `json` files in the
in the `/templates` directory. This is the `jinja2` template, and it will be
passed the same context as the regular pages (so this can be used to
add conference-global things) as well as a structure called `reg` that
contains the current registration. To view an example of this `reg`
structure, generate an attendee report (using the regular reporting
system) in format `json`.

At the root of the json structure, two elements have to be defined:
width and height. All positions and sizes are defined in mm.

If the element `border` is set to *true*, a thin black border will be
drawn around the outer edges (for cutting). If the element
is set to *false*, no border will be printed. If the element is not set
at all, printing will be controlled from the form field when building the
badges, and be off when building tickets.

If the element `forcebreaks` is set to *true*, a pagebreak will be forced
between each badge, making sure there is only one badge per
page. If it's set to *false*,  as many badges as possible will be
added to a page. If the element is not set at all, page breaks will be
controlled from the form field when building the badges. For tickets,
only one page is ever printed.

Finally, an element called `elements` must exist, and contain an *array
of objects*. Each of these objects represents something to be drawn on
the badge, and will be drawn in order.

The currently supported element types are:

box
:  draws an empty or filled rectangle

line
   draws a straight line

image
:  draws an image (which must be in the /static subdirectory)

qrimage
:  draws a qr code image

paragraph
:  draws a dynamically sized paragraph of text

All elements require that the parameters `x`, `y`, `width` and
`height` are specified, except for `line` where `width` and
`height` can be optional. Further attributes depend on the element:

box
:    fill
     : Color to fill with. Leave empty for no fill.

	 stroke
	 : Set to true to draw a line around the box (and not just fill)

line
:    x2, y2
     : Can be specified *instead of* `width` and `height`, but not together with.

image
:    src
     : Path (relative to `/static`) to PNG image

     mask
	 : Mask to use (defaults to *auto*)

     preserveAspect
	 : Set to true to preserve aspect ratio

qrimage
:    qrcontent
	 : The text string to be turned into a QR code

paragraph
:    text
     : The actual text to write

     font
     : The font to use. This font must be regsitered in local_settings.py!

     color
	 : The color to use (defaults to *black*)

     bold
	 : Use a bold font (defaults to *false*)

     maxsize
	 : Maximum size to use for dynamically sized font

     align
	 : Alignment (*left* (default), *right*, *center*)

Color are specified either by name (*white*, *black*) or by RGB value
in the form of an array containing [r,b,g] color values (0-255).


## Badges

To build the badges, use the Attendee Report feature, and select
output format as `badge`.

## Tickets

Tickets are automatically generated and emailed to users along with
the welcome email as [configured](configuring).

They can also be downloaded from the attendee registration dashboard,
or be previewed from the administration view of an attendee. In both
these cases the ticket is re-rendered, so in case the template has
changed, the ticket will also change (but of course existing emailed
tickets can't be changed).

## Testing

To test badges and tickets, the `postgresqleu/confreg/jinjapdf.py` file can be
run independently. It does not depend on django (but does require `jinja2`
and reportlab, of course) or the rest of the repository structure, so
it's recommended that a new version of this file is simply downloaded
from the main repository when testing (rather than adding it to a
conference specific repository).

To get attendee data to test the badges on, use the `json` format
attendee report and save it to a file. Then run the script:

    jinjapdf.py badge /path/to/repo /path/to/attendees.json /path/to/badges.pdf

The repository path should be the root of the repository, the same one
used for `deploystatic.py`.

Test test a ticket layout, use the same script, just for tickets:

    jinjapdf.py ticket /path/to/repo /path/to/attendees.json /path/to/badges.pdf

It's easiest to use the same JSON output as for badges, in which case
the first entry will be used.

To access conference data, a second JSON file can be used, and
specified with the `--confjson /some/where.json` parameter. The
contents of this JSON file will be added to the `conference` object
available from the template. The content of the file should look
something like:

	{
		"conferencename": "Test Conference",
		"conferencedatestr": "2018-12-26",
		"location": "Somewhere"
	}
