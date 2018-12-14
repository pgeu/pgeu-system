#!/usr/bin/env python
#
# This script fakes an Adyen notification of different kinds, including
# sending it with correct passwords and such things.
# Clearly - use with care!
#
#
# Copyright (C) 2013, PostgreSQL Europe
#

import os
import sys
import base64
import urllib
import urllib2

# Set up for accessing django
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../'))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "postgresqleu.settings")
import django
django.setup()

from django.conf import settings


if __name__=="__main__":
    body = ""
    if len(sys.argv)==3 and sys.argv[1] == "raw":
        body = raw_input('Enter the http POST data as a single string: ')
    elif len(sys.argv)==3 and sys.argv[1] == "prompt":
        fields = ('merchantAccountCode', 'pspReference', 'merchantReference', 'originalReference', 'eventDate', 'eventCode', 'paymentMethod', 'live', 'success', 'value', 'currency', 'reason', )
        vals = {}
        for f in fields:
            vals[f] = raw_input('%s:' % f)
        body = urllib.urlencode(vals)
    else:
        print "Usage: fake_notification.py <raw|prompt> <baseurl>"
        sys.exit(1)

    print "'%s'\n" % body
    base = sys.argv[2]
    url = "%s/p/adyen_notify/" % base
    while True:
        r = raw_input("Are you sure you want to send this notification to %s ?" % url)
        if r.lower().startswith('y'):
            break
        if r.lower().startswith('n'):
            sys.exit(0)

    req = urllib2.Request(url, body)
    req.add_header("Authorization", "Basic %s" % (
        base64.encodestring("%s:%s" % (
            settings.ADYEN_NOTIFY_USER,
            settings.ADYEN_NOTIFY_PASSWORD,
        )).replace('\n', '')))
    try:
        resp = urllib2.urlopen(req)
        print resp.read()
    except urllib2.HTTPError, e:
        print "Error %s from server" % e.code
        with open('/tmp/fake_notify_error.txt', 'w') as f:
            f.write(e.read())
        print "Content written to /tmp/fake_notify_error.txt"

