#!/usr/bin/env python3

import argparse
import datetime
import jinja2
import json


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Get session info from filename")
    parser.add_argument('jsonschedule', type=argparse.FileType(), help='JSON Schedule file')
    parser.add_argument('filenametemplate', type=str, help='Jinja2 template to generate filenames')
    parser.add_argument('filenames', type=str, nargs='+', help='Filename to look up')
    parser.add_argument('--statefile', type=argparse.FileType(), help='State file')
    args = parser.parse_args()

    jsonschedule = json.load(args.jsonschedule)
    if args.statefile:
        state = json.load(args.statefile)
    else:
        state = None

    env = jinja2.Environment()
    fntemplate = env.from_string(args.filenametemplate)

    matches = {}
    for d in jsonschedule['days']:
        dat = datetime.datetime.strptime(d['day'], '%Y-%m-%d').date()

        for s in d['sessions']:
            if s.get('empty', False):
                continue

            s['starttime'] = datetime.datetime.fromisoformat(s['starttime'])
            s['endtime'] = datetime.datetime.fromisoformat(s['endtime'])

            fn = fntemplate.render({'day': dat, 'session': s})
            if fn:
                matches[fn] = s

    for fn in args.filenames:
        if fn in matches:
            s = matches[fn]
            if state and str(matches[fn]['id']) in state['sessions']:
                print("{}: {} (session {}, videoids {})".format(fn, s['title'], s['id'], state['sessions'][str(s['id'])]))
            else:
                print("{}: {} (session {})".format(fn, s['title'], s['id']))
        else:
            print("{} not matched".format(fn))
