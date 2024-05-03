#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Fetch sponsor images from benefits in pgeu-system
#

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.request


# Slugify the names - needs to be compatible with django/jinja/deploystatic
def slugify(value):
    if not value:
        return ''
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch pgeu-system sponsor files from token URLs')
    parser.add_argument('tokenurl', type=str, help='Base URL including the token value, but not including the type of dta')
    parser.add_argument('directory', type=str, help='Destination directory')
    parser.add_argument('benefitname', type=str, help='Benefit name to match')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--verbose', action='store_true')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print("{} is not a directory.".format(args.directory))
        sys.exit(1)

    with urllib.request.urlopen('{}/sponsorclaims.json'.format(args.tokenurl.rstrip('/'))) as resp:
        data = json.load(resp)

        for name, sponsorinfo in data['sponsors']['sponsors'].items():
            for benefit in sponsorinfo['benefits']:
                if benefit['name'] == args.benefitname:
                    filename = os.path.join(args.directory, '{}.png'.format(slugify(name)))
                    if os.path.isfile(filename):
                        # Check if this file is unchanged
                        with open(filename, 'rb') as f:
                            # We assume we can just put it all in memory without a problem
                            currhash = hashlib.md5(f.read()).hexdigest()
                        if currhash == benefit['claim']['image']['tag']:
                            if args.verbose:
                                print("{} unmodified.".format(filename))
                            break
                        if not args.overwrite:
                            print("File {} has changed, NOT overwriting".format(filename))
                            break
                        if args.verbose:
                            print("File {} has changed, re-downloading".format(filename))

                    with urllib.request.urlopen('{}/sponsorclaims.json{}'.format(
                            args.tokenurl.strip('/'),
                            benefit['claim']['image']['suburl'],
                    )) as fresp:
                        with open(filename, 'wb') as f:
                            shutil.copyfileobj(fresp, f)
                    print("Downloaded {}".format(filename))
