#!/usr/bin/env python3

import argparse
import datetime
import json
import os
import requests
import sys

from videoutil import get_current_token

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Get session info from filename")
    parser.add_argument('statefile', type=str, help='State file')
    parser.add_argument('sessionid', type=int, help='Session id to delete video for')
    args = parser.parse_args()

    if not os.path.isfile(args.statefile):
        print("{} not found".format(args.statefile))
        sys.exit(1)

    with open(args.statefile) as f:
        state = json.load(f)

    if str(args.sessionid) not in state['sessions']:
        print("Session {} not found in state.".format(args.sessionid))
        sys.exit(1)

    videoid = state['sessions'][str(args.sessionid)]['youtube']

    while True:
        r = input("Delete youtube video {}? ".format(videoid)).lower()
        if r in ('n', 'no'):
            print("Not deleting.")
            sys.exit(0)
        elif r in ('y', 'yes'):
            break

    token = get_current_token()
    sess = requests.Session()
    sess.headers['Authorization'] = 'Bearer {}'.format(token)

    print("Deleting video {}".format(videoid))
    r = sess.delete('https://www.googleapis.com/youtube/v3/videos?id={}'.format(videoid))
    r.raise_for_status()
    if r.status_code != 204:
        print("Invalid status of delete: {}".format(r.status_code))
        sys.exit(1)

    print("Deleted.")
    del state['sessions'][str(args.sessionid)]['youtube']
    if not state['sessions'][str(args.sessionid)]:
        del state['sessions'][str(args.sessionid)]
    with open(args.statefile, 'w') as f:
        json.dump(state, f)
