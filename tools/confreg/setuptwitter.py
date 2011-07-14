#!/usr/bin/env python
# vim: ai ts=4 sts=4 sw=4
"""PostgreSQL Planet Aggregator

This file contains simpler wrapper for getting the oauth credentials
to set up the twitter access.

Copyright (C) 2010 PostgreSQL Global Development Group
"""

import sys
import oauth2 as oauth
import cgi
import ConfigParser

cfg = ConfigParser.ConfigParser()
cfg.read('twitter_sync.ini')

if not cfg.has_option('twitter', 'consumer') or not cfg.has_option('twitter', 'consumersecret'):
	print "Before you can run this, you need to register an application at"
	print "developer.twitter.com and put the consumer and consumersecret values"
	print "in the [twitter] section of twitter_sync.ini."
	sys.exit(1)

consumer = oauth.Consumer(cfg.get('twitter', 'consumer'), cfg.get('twitter', 'consumersecret'))
client = oauth.Client(consumer)
resp, content = client.request("https://api.twitter.com/oauth/request_token", "GET")
if resp['status'] != '200':
	print "request_token call failed!"
	print resp
	sys.exit(1)
req_token_cred = dict(cgi.parse_qsl(content))

print "Received request token."
print "Token secret: %s" % req_token_cred['oauth_token_secret']
print ""
print "Now, go to the following URL:"
print "https://api.twitter.com/oauth/authorize?oauth_token=%s" % req_token_cred['oauth_token']
print ""

pin = raw_input('Enter the PIN here:')

token = oauth.Token(req_token_cred['oauth_token'], req_token_cred['oauth_token_secret'])
client = oauth.Client(consumer, token)
# Put the PIN on the URL, because it seems to not work to use token.set_verifier()
resp, content = client.request('https://api.twitter.com/oauth/access_token?oauth_verifier=%s' % pin, "POST")
if resp['status'] != '200':
	print "access_token failed!"
	print resp
	print content
	sys.exit(1)

r = dict(cgi.parse_qsl(content))
print "Access token received."
print "Token: %s" % r['oauth_token']
print "Secret: %s" % r['oauth_token_secret']
print "Record these two values in the database, and you're good to go!"
