#!/usr/bin/env python
#
# Tool to synchronize conference attendees with a mailman mailinglist
#

import ConfigParser
import urllib2
from urllib import urlencode
import re
import psycopg2

class MailmanSynchronizer(object):
	def __init__(self, url, password, dryrun=False):
		self.url = url
		self.password = password
		self.current_recipients = []
		self.dryrun = dryrun

	def set_list(self, recipientlist):
		self.recipientlist = set(recipientlist)

	def sync(self):
		self._fetch_current_list()
		if self.current_recipients == self.recipientlist:
			#print "List is up-to-date."
			return

		to_add = self.recipientlist.difference(self.current_recipients)
		to_remove = self.current_recipients.difference(self.recipientlist)

		if to_add:
			self._bulk_process('members/add', {
				'subscribees': "\n".join(to_add),
				'subscribe_or_invite': '0',
				'send_welcome_msg_to_this_batch': '1',
				'send_notifications_to_list_owner': '1',
			})
			print "Added users %s to the list." % to_add

		if to_remove:
			self._bulk_process('members/remove', {
				'unsubscribees': "\n".join(to_remove),
				'send_unsub_ack_to_this_batch': '1',
				'send_unsub_notifications_to_list_owner': '1',
			})
			print "Removed users %s from the list." % to_remove

	def _bulk_process(self, suburl, parameters):
		if self.dryrun:
			return
		r = self._make_request(suburl, parameters)
		r.read()
		# Ignore the result, just assume it worked :-)

	def _make_request(self, suburl, parameters=None):
		p = { 'adminpw': self.password, }
		if parameters:
			p.update(parameters)
		req = urllib2.Request("%s/%s" % (self.url, suburl), urlencode(p))
		return urllib2.urlopen(req)

	def _fetch_current_list(self):
		r = self._make_request("members")
		s = r.read()
		if not s.find("Membership&nbsp;Management...")>0:
			raise Exception("Could not access membership list")
		# Parse the HTML for the list of members
		alist = re.findall('<INPUT name="([^"]+%40[^"]+)_unsub" type', s)
		self.current_recipients = set([s.replace('%40','@').replace('%2B','+') for s in alist])

c = ConfigParser.ConfigParser()
c.read("mailman_sync.ini")

db = psycopg2.connect(c.get('settings','db'))
curs = db.cursor()

# Synchronize attendee-lists
curs.execute("SELECT id, listadminurl, listadminpwd FROM confreg_conference WHERE active AND NOT (listadminurl='' OR listadminpwd='')")
for confid, url, pwd in curs.fetchall():
	#print "Synchronizing list %s" % url
	c2 = db.cursor()
	c2.execute("""SELECT email FROM confreg_conferenceregistration cr 
		INNER JOIN confreg_registrationtype rt ON cr.regtype_id=rt.id 
		WHERE cr.conference_id=%(id)s AND cr.payconfirmedat IS NOT NULL AND rt.inlist""",
		{'id': confid, }
	)
	ms = MailmanSynchronizer(url,pwd)
	ms.set_list(set([r[0].lower() for r in c2.fetchall()]))
	ms.sync()

# Now do any potential speaker lists
curs.execute("SELECT id, speakerlistadminurl, speakerlistadminpwd FROM confreg_conference WHERE active AND NOT (speakerlistadminurl='' OR speakerlistadminpwd='')")
for confid, url, pwd in curs.fetchall():
	#print "Synchronizing list %s" % url
	c2 = db.cursor()
	c2.execute("""SELECT DISTINCT email FROM auth_user au
        INNER JOIN confreg_speaker s ON au.id=s.user_id
        INNER JOIN confreg_conferencesession_speaker csp ON csp.speaker_id=s.id
        INNER JOIN confreg_conferencesession cs ON cs.id=csp.conferencesession_id
        WHERE cs.conference_id=%(id)s AND cs.status=1""",
			   { 'id': confid, }
    )
	ms = MailmanSynchronizer(url,pwd)
	ms.set_list(set([r[0].lower() for r in c2.fetchall()]))
	ms.sync()

