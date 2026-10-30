#!/usr/bin/env python3

import argparse
import json
import os
import sys

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Generate list of videos for review")
    parser.add_argument('statefile', type=str, help='State file')
    parser.add_argument('schedulefile', type=str, help='Schedule file')

    args = parser.parse_args()

    if not os.path.isfile(args.statefile):
        print("{} not found".format(args.statefile))
        sys.exit(1)

    if not os.path.isfile(args.schedulefile):
        print("{} not found".format(args.schedulefile))
        sys.exit(1)

    with open(args.statefile) as f:
        state = json.load(f)

    with open(args.schedulefile) as f:
        schedule = json.load(f)

    for ssessionid, videos in state['sessions'].items():
        sessionid = int(ssessionid)

        # Find the session
        for d in schedule['days']:
            for s in d['sessions']:
                if s['sessionid'] == sessionid:
                    videolinks = []
                    for provider, videoid in videos.items():
                        if provider == 'youtube':
                            videolinks.append('https://www.youtube.com/watch?v={}'.format(videoid))
                        else:
                            print("Video provider {} is unknown".format(provider))
                            sys.exit(1)
                    print("{};{};{}".format(sessionid, s['title'].replace(';', ','), ";".join(videolinks)))
                    break
            else:
                continue
            break
        else:
            print("Session {} not found in schedule".format(sessionid))
            sys.exit(1)
