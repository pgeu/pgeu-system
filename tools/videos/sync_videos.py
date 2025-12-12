#!/usr/bin/env python3

import argparse
import datetime
import jinja2
import json
import os
import requests
import sys

from videoutil import get_current_token


def get_videos_in_playlist(args, sess):
    pagetoken = None
    while True:
        r = sess.get('https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={}{}&maxResults=50'.format(
            args.playlist,
            '&pageToken={}'.format(pagetoken) if pagetoken else '',
        ))
        r.raise_for_status()
        j = r.json()
        yield from [v['snippet']['resourceId']['videoId'] for v in j['items']]
        if 'nextPageToken' in j:
            pagetoken = j['nextPageToken']
        else:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Sync videos with youtube and sessions")
    parser.add_argument('statefile', type=str, help='State file')
    parser.add_argument('jsonschedule', type=argparse.FileType(), help='JSON Schedule file')
    parser.add_argument('videodirectory', type=str, help='Directory with video files')
    parser.add_argument('filenametemplate', type=str, help='Jinja2 template to generate filenames')
    parser.add_argument('--skiptracks', type=str, nargs='+', help='Tracks to skip')
    parser.add_argument('--tags', type=str, nargs='+', help='Tags to add')
    parser.add_argument('--playlist', type=str, help='Youtube playlist to sync to (will upload files as necessary)')
    parser.add_argument('--privacy', default='private', choices=('private', 'unlisted', 'public'), help='Privacy status for all videos')
    parser.add_argument('--thumbnails', type=str, help='Directory with thumbnail images to upload')
    parser.add_argument('--titletemplate', type=str, help='Template to apply to titles', default='{{ session.speakers|map(attribute="name")|join(", ") }}: {{ session.title }}')
    parser.add_argument('--bodytemplate', type=str, help='Template to apply to bodies', default='{{ session.abstract }}')
    parser.add_argument('--verbosediff', action='store_true', help='Show both old and new value on updates (can be very long)')
    args = parser.parse_args()

    jsonschedule = json.load(args.jsonschedule)

    if not os.path.isdir(args.videodirectory):
        print("{} is not a directory".format(args.videodirectory))
        sys.exit(1)

    if args.thumbnails and not os.path.isdir(args.thumbnails):
        print("{} is not a directory".format(args.thumbnails))
        sys.exit(1)

    if os.path.isfile(args.statefile):
        with open(args.statefile, 'r') as f:
            state = json.load(f)
    else:
        state = {
            'sessions': {},
        }

    def flush_state():
        with open(args.statefile, 'w') as f:
            json.dump(state, f)

    env = jinja2.Environment()
    fntemplate = env.from_string(args.filenametemplate)
    titletemplate = env.from_string(args.titletemplate)
    bodytemplate = env.from_string(args.bodytemplate)

    skiptracks = list(map(str.lower, args.skiptracks))

    matches = {}
    noconsent = []
    noconsentfiles = []
    unmatched_files = []
    unmatched_sessions = []
    # Forward match from sessions
    for d in jsonschedule['days']:
        dat = datetime.datetime.strptime(d['day'], '%Y-%m-%d').date()

        for s in d['sessions']:
            if s.get('empty', False):
                continue

            if s.get('track', {}).get('trackname', '').lower() in skiptracks:
                continue

            s['starttime'] = datetime.datetime.fromisoformat(s['starttime'])
            s['endtime'] = datetime.datetime.fromisoformat(s['endtime'])

            fn = fntemplate.render({'day': dat, 'session': s})
            if not fn:
                continue

            if os.path.isfile(os.path.join(args.videodirectory, fn)):
                matches[fn] = s
                if not s['recordingconsent']:
                    noconsent.append(s)
                    noconsentfiles.append(fn)
            else:
                unmatched_sessions.append(s)

    unmatched_files = set(os.listdir(args.videodirectory)).difference(set(matches.keys()))

    if unmatched_sessions:
        print("Could not find video files for these sessions:")
        for s in unmatched_sessions:
            print("{}: {}".format(s['starttime'], s['title']))

    if unmatched_files:
        print("Could not find sessions matching these files:")
        for f in unmatched_files:
            print(f)

    if noconsent:
        print("The following sessions LACK recording consent:")
        for s in noconsent:
            print("{} in track {} by {}".format(
                s['title'],
                s.get('track', {}).get('trackname', 'No track'),
                ", ".join(sp['name'] for sp in s['speakers']),
            ))

    if args.playlist:
        try:
            token = get_current_token()

            print("----- Syncing with youtube -----")
            sess = requests.Session()
            sess.headers['Authorization'] = 'Bearer {}'.format(token)

            # Enumerate all playlist members
            videosInPlaylist = list(get_videos_in_playlist(args, sess))

            for fn, session in matches.items():
                if fn in noconsentfiles:
                    print("Skipping {}, no recording consent".format(fn))
                    continue

                ssid = str(session['id'])

                videodata = {
                    'snippet': {
                        'categoryId': str(28),
                        'title': titletemplate.render({'session': session})[:100].strip(),
                        'description': bodytemplate.render({'session': session}).replace('<', b'\xef\xbc\x9c'.decode()).replace('>', b'\xef\xbc\x9e'.decode()),
                        'defaultLanguage': 'en',
                        'defaultAudioLanguage': 'en',
                        'tags': sorted(args.tags),
                    },
                    'status': {
                        'selfDeclaredMadeForKids': False,
                        'privacyStatus': args.privacy,
                        'license': 'creativeCommon',
                        'containsSyntheticMedia': False,
                    },
                    'recordingDetails': {
                        'recordingDate': s['starttime'].strftime('%Y-%m-%dT00:00:00Z'),
                    }
                }
                if ssid not in state['sessions']:
                    print("Session {} ({}) not uploaded, uploading now...".format(ssid, session['title']))
                    r = sess.post('https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status,recordingDetails&notifySubscribers=False&uploadType=resumable',
                                  json=videodata,
                                  headers={
                                      'slug': fn,
                                  })
                    if r.status_code != 200:
                        print("Failed to upload video in stage 1: status {}".format(r.status_code))
                        print(r.text)
                        sys.exit(1)

                    with open(os.path.join(args.videodirectory, fn), 'rb') as f:
                        r2 = sess.post(r.headers['Location'], data=f)
                        if r2.status_code not in (200, 201):
                            print("Failed to upload video in stage 2: status {}".format(r.status_code))
                            print(r.text)
                            print("You probably have to manually go remove the partial upload!")
                            sys.exit(1)

                        j = r2.json()
                        videoid = j['id']

                        # Uploaded, so store our state!
                        state['sessions'][ssid] = {"youtube": videoid}
                        flush_state()

                        # Do we have thumbnail(s)?
                        if args.thumbnails:
                            basefn = os.path.join(args.thumbnails, os.path.splitext(fn)[0])
                            for ext in ('png', 'jpg', 'jpeg'):
                                thumbfn = '{}.{}'.format(basefn, ext)
                                if os.path.isfile(thumbfn):
                                    print("Uploading thumbnail {}".format(thumbfn))
                                    with open(thumbfn, 'rb') as f:
                                        r = sess.post('https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={}'.format(videoid), data=f)
                                        r.raise_for_status()
                                    break
                else:
                    videoid = state['sessions'][ssid]['youtube']
                    r = sess.get('https://www.googleapis.com/youtube/v3/videos?id={}&part=snippet,status,recordingDetails'.format(videoid))
                    r.raise_for_status()
                    j = r.json()
                    data = j['items'][0]  # Assume always one match
                    changed = False
                    for k, v in videodata.items():
                        for k2, v2 in v.items():
                            # For some reason this one is not returned back, so we can't update it -- but we could set it from the beginning
                            if k2 == 'containsSyntheticMedia':
                                continue
                            if data[k].get(k2, '') != v2:
                                print("{}.{} of session {} changed".format(k, k2, ssid))
                                if args.verbosediff:
                                    print("Old: '{}'".format(data[k].get(k2, '')))
                                    print("New: '{}'".format(v2))
                                changed = True

                    if changed:
                        print("Updating session {}, video {}".format(ssid, videoid))
                        r = sess.put('https://www.googleapis.com/youtube/v3/videos?part=snippet,status,recordingDetails', json=videodata | {'id': videoid})
                        r.raise_for_status()

                if videoid not in videosInPlaylist:
                    print("Video {} not in playlist, adding".format(videoid))
                    r = sess.post('https://www.googleapis.com/youtube/v3/playlistItems?part=snippet', json={
                        'snippet': {
                            'playlistId': args.playlist,
                            'resourceId': {
                                'kind': 'youtube#video',
                                'videoId': videoid,
                            },
                        },
                    })
                    r.raise_for_status()

        except requests.exceptions.HTTPError as e:
            print("HTTP error {} when calling youtube API:".format(e.response.status_code))
            try:
                print(e.response.json())
            except Exception:
                print(e.response.text)
            sys.exit(1)
    print("Done.")
