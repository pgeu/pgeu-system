#!/usr/bin/env python
#
# Tool to synchronize conference attendees with twitter lists
#

import ConfigParser
import psycopg2
import sys
from twitterclient import TwitterClient

class TwitterConfWrapper(object):
	# do a wrapper so we can use the planet interface unmodified

	def __init__(self, cparser, user, listname, token, secret):
		self.cparser = cparser
		self.user = user
		self.listname = listname
		self.token = token
		self.secret = secret

	def get(self, section, setting):
		if not section=='twitter':
			raise Exception("Don't know how to handle this section")
		if setting == "account":
			return self.user
		if setting == "listname":
			return self.listname
		if setting == "token":
			return self.token
		if setting == "secret":
			return self.secret
		return self.cparser.get(section, setting)

class TwitterListSync(TwitterClient):
	def __init__(self, cparser, user, listname, token, secret, members):
		self.confwrap = TwitterConfWrapper(cparser, user, listname,
										   token, secret)
		self.members = set([self._normalize_handle(r[0]) for r in members])

		TwitterClient.__init__(self, self.confwrap)

	def _normalize_handle(self, handle):
		h = handle.lower()
		if h[0] == '@': h = h[1:]
		return h

	def run(self):
		current = set([t.lower() for t in self.list_subscribers()])

		map(self.remove_subscriber, current.difference(self.members))
		map(self.add_subscriber, self.members.difference(current))


if __name__=="__main__":
	c = ConfigParser.ConfigParser()
	c.read("twitter_sync.ini")

	db = psycopg2.connect(c.get('settings','db'))
	curs = db.cursor()

	# Look for any conflicts
	curs.execute("SELECT twitter_user, count(conferencename) FROM confreg_conference WHERE twittersync_active AND NOT twitter_user='' GROUP BY twitter_user HAVING count(*) > 1")
	dupes = curs.fetchall()
	if dupes:
		print "Twitter user %s is duplicated for multiple active conference. Twitter sync disabled."
		sys.exit(1)

	# Figure out lists to sync
	curs.execute("SELECT id, twitter_user, twitter_attendeelist, twitter_speakerlist, twitter_sponsorlist, twitter_token, twitter_secret FROM confreg_conference WHERE twittersync_active AND NOT (twitter_user IS NULL OR twitter_user='')")
	for confid, user, attlist, spklist, sponsorlist, token, secret in curs.fetchall():
		if attlist:
			# Synchronize the attendee list
			curs.execute("""SELECT DISTINCT twittername FROM confreg_conferenceregistration cr
		                   INNER JOIN confreg_registrationtype rt ON cr.regtype_id=rt.id
		                   WHERE cr.conference_id=%(id)s AND cr.payconfirmedat IS NOT NULL AND rt.inlist
						   AND NOT (twittername='' OR twittername IS NULL)""",
						{'id': confid, }
						)
			TwitterListSync(c, user, attlist, token, secret,
							curs.fetchall()).run()

		if spklist:
			curs.execute("""SELECT DISTINCT twittername FROM auth_user au
               INNER JOIN confreg_speaker s ON au.id=s.user_id
               INNER JOIN confreg_conferencesession_speaker csp ON csp.speaker_id=s.id
               INNER JOIN confreg_conferencesession cs ON cs.id=csp.conferencesession_id
               WHERE cs.conference_id=%(id)s AND cs.status=1
				AND NOT (twittername='' OR twittername IS NULL)""",
						 { 'id': confid, }
						 )
			TwitterListSync(c, user, spklist, token, secret,
							curs.fetchall()).run()

		if sponsorlist:
			curs.execute("SELECT DISTINCT twittername FROM confsponsor_sponsor WHERE conference_id=%(id)s AND confirmed", {
				'id': confid,
				})

			TwitterListSync(c, user, sponsorlist, token, secret,
							curs.fetchall()).run()
