#!/usr/bin/env python3

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

import jinja2

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Create PNGs from SVG templates")
    parser.add_argument('template', type=argparse.FileType(), help='Template file')
    parser.add_argument('outdir', type=str, help='Output directory')
    parser.add_argument('filenametemplate', type=str, help='Jinja2 template to generate filenames')
    parser.add_argument('jsonschedule', type=str, help='Pointer to schedule JSON dump, will loop over sessions')
    parser.add_argument('--skiptracks', type=str, nargs='+', help='Tracks to skip')

    args = parser.parse_args()

    if args.jsonschedule:
        with open(args.jsonschedule) as f:
            data = json.load(f)
    else:
        print("Must specify source")
        sys.exit(1)

    if not os.path.isdir(args.outdir):
        print("{} is not a directory".format(args.outdir))
        sys.exit(1)

    skiptracks = list(map(str.lower, args.skiptracks))

    fnenv = jinja2.Environment()
    fntemplate = fnenv.from_string(args.filenametemplate)

    env = jinja2.Environment(autoescape=True)
    template = env.from_string(args.template.read())

    for d in data['days']:
        d['day'] = datetime.datetime.strptime(d['day'], '%Y-%m-%d').date()

        for s in d['sessions']:
            if s.get('empty', False):
                continue

            if s.get('track', {}).get('trackname', '').lower() in skiptracks:
                continue

            s['starttime'] = datetime.datetime.fromisoformat(s['starttime'])
            s['endtime'] = datetime.datetime.fromisoformat(s['endtime'])

            svg = template.render({
                'day': d['day'],
                'session': s,
            })

            # We'd like to use cairosvg, but it doesn't support things like linebreaks. For more total svg
            # support, we run inkscape in a pipe, which is ugly but works.
            with tempfile.NamedTemporaryFile(suffix='.svg', mode='w', encoding='utf-8') as f:
                f.write(svg)
                f.flush()
                subprocess.run([
                    'inkscape',
                    '--export-type=png',
                    '--export-area-page',
                    '--export-filename',
                    os.path.join(args.outdir, fntemplate.render({
                        'day': d['day'],
                        'session': s,
                        'fullschedule': data,
                    })),
                    f.name], check=True)
