# Image generation

The system comes with a trivial tool to generate images for each
session in the system. This can be used to for example generate
screens to show on monitors outside the conference rooms, or to
generate slides to show in the rooms in between talks.

Source data is the json schedule dump that's either downloaded using a
button on the dashboard or using a token-url.

Each image gets a template in SVG format that can take jinja2 markup
in it, to generate the images. The tool will by default loop over all
sessions that have a time set. Use `--skiptracks` to exclude specific
tracks such as breaks from generation.

To generate the images ther jinja2 code is applied to generate a
temporary svg file and it will then launch `inkscape` to create an
export. Using cairosvg would be better but the SVG support there is
just not good enough, such as not supporting linebreaks.
