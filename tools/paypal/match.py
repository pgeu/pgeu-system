#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This script attempts to match records in the database to some sort of payments,
# and flag them as matched in the database.
#
# Could be made nice and plugin:able with separate subsystems in separate files,
# but we really don't expect that many subsystems. So for now there's just
# a function for each subsystem.
#
# Note that matching functions need to be added in the order of most selective
# first, in case there is any risk of overlap.
#
# Copyright (C) 2010, PostgreSQL Europe
#

from datetime import datetime, timedelta, date
import psycopg2
import psycopg2.extras
import re
import sys
import ConfigParser

from subprocess import Popen, PIPE
from email.mime.text import MIMEText

mailqueue = []

cfg = ConfigParser.ConfigParser()
cfg.read('paypal.ini')

# Generic logging class for matcher functions
class MatchLogger(object):
	def __init__(self, db, row, title):
		self.db = db
		self.row = row
		self.title = title

	def log(self, message):
		cursor = db.cursor()
		cursor.execute("""INSERT INTO paypal_errorlog ("timestamp", message, sent)
VALUES (CURRENT_TIMESTAMP, %(message)s, 'f')""", {
				'message': 'Paypal %s by %s (%s) on %s: %s: %s' % (
					self.row['paypaltransid'],
					self.row['sender'],
					self.row['sendername'],
					self.row['timestamp'],
					self.title,
					message
				)
		})


# This array holds all functions used to match different types of payments
matchers = []

############
# Membership payments
############
member_matchre = re.compile('^PostgreSQL Europe - 2 years membership - (\S+)$')
def match_membership(db, row):
	match = member_matchre.match(row['transtext'])
	if not match:
		# Not a membership payment
		return False
	email = match.group(1)

	logger = MatchLogger(db, row, "Membership")

	if row['amount'] != 10:
		# Yeah, the amount is hardcoded, that's kind of cheating...
		logger.log("Payment of EUR %s, should be EUR 10! Not approving!")
		return False
	# Look for the user
	cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
	cursor.execute("""
SELECT user_id, paiduntil FROM membership_member
INNER JOIN auth_user ON auth_user.id=user_id
WHERE email=%(email)s""", {
			'email': email,
			})
	res = cursor.fetchall()
	message = ''
	if len(res) == 0:
		# Membership payment, but no matching email address. We will retry this
		# match again later, but log an error just in case.
		logger.log("Payment for non-registered email %s, will retry later!")
		return False
	elif len(res) != 1:
		# Matched invalid number of users. Flag as matched with an error message.
		message = 'Matched invalid number of users (%s)' % len(res)
	else:
		# Matched a user, let's look at increasing the date for him
		if res[0]['paiduntil'] and res[0]['paiduntil'] > date.today() + timedelta(days=60):
			# Cannot renew this membership yet, probably a parsing error somewhere?
			message = 'Matched already paid membership until %s' % res[0]['paiduntil']
		else:
			# Yes, we can renew it. So let's do that.
			cursor.execute("""
UPDATE membership_member
SET paiduntil=COALESCE(paiduntil,CURRENT_DATE)+'2 years'::interval,
    membersince=COALESCE(membersince,CURRENT_DATE)
WHERE user_id=%(id)s
RETURNING paiduntil""", {
					'id': res[0]['user_id'],
					})
			paiduntil = cursor.fetchall()[0]['paiduntil']
			cursor.execute("""
INSERT INTO membership_memberlog (member_id, "timestamp", message)
VALUES (%(id)s, CURRENT_TIMESTAMP, %(message)s)""", {
					'id': res[0]['user_id'],
					'message': 'Payment for 2 years received, membership extended to %s. Thank you!' % paiduntil,
			})
			message = 'Extended membership for %s to %s.' % (email, paiduntil)
			msg = MIMEText("""
We have registered your payment of €10, and your membership is now
set to expire on %s.

Thank you!

PostgreSQL Europe
""" % paiduntil, _charset = 'utf-8')
			msg['subject'] = 'Your membership in PostgreSQL Europe'
			msg['from'] = cfg.get('_mail', 'sender')
			msg['to'] = email
			mailqueue.append(msg)

	logger.log(message)
	# Finally, set the payment as matched
	cursor.execute("UPDATE paypal_transactioninfo SET matched='t', matchinfo=%(info)s WHERE id=%(id)s", {
			'id': row['id'],
			'info': message,
			})
	return True
matchers.append(match_membership)


############
# Conference registrations
############
confreg_matchre = re.compile('^([^-]+) - (.*) \(([^)]+)\)$')
def match_confreg(db, row):
	match = confreg_matchre.match(row['transtext'])
	if not match:
		# Not a conference registration payment
		return False
	confname = match.group(1)
	paytype = match.group(2) # both payment type and all options
	email = match.group(3)

	logger = MatchLogger(db, row, "Conference Registration")

	# Lookup a registration in the confreg database for this
	cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
	cursor.execute("""
SELECT reg.id, payconfirmedat, payconfirmedby, cost + COALESCE(
(
  SELECT sum(cost) AS optioncost
  FROM confreg_conferenceregistration_additionaloptions rao
   INNER JOIN confreg_conferenceadditionaloption ao ON ao.id=rao.conferenceadditionaloption_id
   WHERE rao.conferenceregistration_id=reg.id
), 0) AS totalcost
FROM confreg_conferenceregistration reg
INNER JOIN confreg_conference conf ON conf.id=reg.conference_id
INNER JOIN confreg_registrationtype rt ON rt.id=reg.regtype_id
WHERE conf.conferencename=%(confname)s
AND lower(reg.email)=lower(%(email)s)""", {
			'confname': confname,
			'email': email,
			})
	res = cursor.fetchall()
	message = ''
	if len(res) == 0:
		# It is a conference payment, but there was no actual match.
		# We leave this one and will check it again next time in case the
		# registration db has updated.
		logger.log("Payment does not match any registration")
		return False
	elif len(res) == 1:
		# Single match, this really is all that should ever happen
		if row['amount'] != res[0]['totalcost']:
			# amount does not match! Set it as matched, but don't flag as go
			message = 'WARNING: Payment is incorrect amount, should be %s, NOT approving' % res[0]['totalcost']
		else:
			# Amount is correct, approve if not already done so
			if res[0]['payconfirmedat']:
				message = 'NOTICE: Payment already approved by %s at %s' % (res[0]['payconfirmedby'], res[0]['payconfirmedat'])
			else:
				message = 'Matched payment for id %s' % res[0]['id']
				# Also flag the payment in the conference database
				cursor.execute("UPDATE confreg_conferenceregistration SET payconfirmedat=CURRENT_TIMESTAMP, payconfirmedby='paypal' WHERE id=%(id)s", {
						'id': res[0]['id'],
						})
	else:
		# Invalid length
		message = 'WARNING: Matched more than one row (%s), this should never happen! NOT approving!' % len(res)

	logger.log(message)
	# If we got this far, we have a match of some kind at least in a way that we don't want to rescan
	# the payment next time. So set it as matched, and set the match information message.
	cursor.execute("UPDATE paypal_transactioninfo SET matched='t', matchinfo=%(info)s WHERE id=%(id)s", {
			'id': row['id'],
			'info': message,
			})
	return True
matchers.append(match_confreg)


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print "Usage: match.py <dsn>"
		sys.exit(1)

	db = psycopg2.connect(sys.argv[1])
	cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
	cursor.execute('SELECT id, paypaltransid, "timestamp", sourceaccount_id, sender, sendername, amount, transtext FROM paypal_transactioninfo WHERE NOT matched ORDER BY id')
	for r in cursor.fetchall():
		for m in matchers:
			if m(db, r): break # don't continue searching if match was found
	db.commit()

	# Send off the mail queue if there is one
	for msg in mailqueue:
		pipe = Popen("/usr/sbin/sendmail -t", shell=True, stdin=PIPE).stdin
		pipe.write(msg.as_string())
		pipe.close()
