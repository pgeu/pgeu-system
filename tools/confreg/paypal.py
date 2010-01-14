#!/usr/bin/env python

from datetime import datetime, timedelta
import urllib2
from urllib import urlencode
from urlparse import parse_qs
from decimal import Decimal
import sys
import psycopg2
import re
import ConfigParser

matchre = re.compile('^([^-]+) - (.*) \(([^)]+)\)$')

class PaypalTransaction(object):
	def __init__(self, paypalapi, apistruct, i):
		self.message = None
		self.ismatch = False
		self.api = paypalapi

		self.transactionid = apistruct['L_TRANSACTIONID%i' % i][0]
		try:
			self.timestamp = datetime.strptime(apistruct['L_TIMESTAMP%i' % i][0], '%Y-%m-%dT%H:%M:%SZ')
			self.email = apistruct['L_EMAIL%i' % i][0]
			self.amount = Decimal(apistruct['L_AMT%i' % i][0])
			self.name = apistruct['L_NAME%i' % i][0]
		except Exception, e:
			self.message = "Unable to parse: %s" % e

	def __str__(self):
		if self.message:
			return self.message
		return "%s (%s): %s <%s> paid %s" % (
			self.transactionid,
			self.timestamp,
			self.name,
			self.email,
			self.amount,
		)

	def already_processed(self, db):
		cursor = db.cursor()
		cursor.execute("SELECT count(*) FROM confreg_paypaltransactioninfo WHERE paypaltransid=%(id)s", {
			'id': self.transactionid,
		})
		return (cursor.fetchall()[0][0] == 1)

	def fetch_details(self):
		r = self.api.get_transaction_details(self.transactionid)
		self.text = r['SUBJECT'][0]
		if r['L_CURRENCYCODE0'][0] != 'EUR':
			raise Exception("Invalid currency %s" % r['L_CURRENCYCODE0'][0])

	def attempt_match(self, db):
		# First grab the pieces. Format is found in confreg/templatetags/payment_options.py
		# combined_title = "%s - %s (%s)" % (title, paytype, email)
		match = matchre.match(self.text)
		if not match:
			self.message = "Unable to parse '%s': no regexp match"
			return
		confname = match.group(1)
		paytype = match.group(2)
		email = match.group(3)

		# Ok, let's see if we can find a registration for this
		cursor = db.cursor()
		cursor.execute("""
SELECT reg.id, payconfirmedat, payconfirmedby, cost
FROM confreg_conferenceregistration reg
INNER JOIN confreg_conference conf ON conf.id=reg.conference_id
INNER JOIN confreg_registrationtype rt ON rt.id=reg.regtype_id
WHERE conf.conferencename=%(confname)s
AND rt.regtype=%(regtype)s
AND lower(reg.email)=lower(%(email)s)""", {
			'confname': confname,
			'regtype': paytype,
			'email': email,
		})
		res = cursor.fetchall()
		if len(res) == 0:
			# No match found
			self.message = "NOTICE: Found no match for this payment"
		elif len(res) == 1:
			# Found a match!
			# Now verify the amount
			if self.amount != res[0][3]:
				self.message = "WARNING: Payment is incorrect amount, should be %s" % res[0][3]
			else:
				# Amount is correct, check if the thing is already approved
				if res[0][2]:
					self.message = "NOTICE: Payment already approved by %s at %s" % (res[0][2], res[0][1])
					self.ismatch = True
				else:
					self.message = "Matched payment for id %s" % res[0][0]
					cursor.execute("UPDATE confreg_conferenceregistration SET payconfirmedat=CURRENT_TIMESTAMP,payconfirmedby='paypal' WHERE id=%(id)s", {
						'id': res[0][0],
					})
					self.ismatch = True
		else:
			self.message = "WARNING: Matched more than one row (%s)!" % len(res)

		print self.message

	def store(self, db):
		cursor = db.cursor()
		cursor.execute("""
INSERT INTO confreg_paypaltransactioninfo
(paypaltransid, "timestamp", sender, sendername, amount, transtext, matched, matchinfo)
VALUES (%(id)s, %(ts)s, %(sender)s, %(name)s, %(amount)s, %(text)s, %(matched)s, %(matchinfo)s)""", {
		'id': self.transactionid,
		'ts': self.timestamp,
		'sender': self.email,
		'name': self.name,
		'amount': self.amount,
		'text': self.text,
		'matched': self.ismatch,
		'matchinfo': self.message or 'WARNING: Failure in parsing somewhere, message not set',
	})

class PaypalAPI(object):
	def __init__(self, apiuser, apipass, apisignature):
		self.API_ENDPOINT = 'https://api-3t.paypal.com/nvp'
		self.apiuser = apiuser
		self.apipass = apipass
		self.apisignature = apisignature
		self.accessparam = {
			'USER': self.apiuser,
			'PWD': self.apipass,
			'SIGNATURE': self.apisignature,
			'VERSION': '56',
		}

	def get_transaction_list(self, firstdate = datetime.now()-timedelta(days=30)):
		ret = self._api_call('TransactionSearch', {
			'STARTDATE': self._dateformat(firstdate),
			'TRANSACTIONCLASS': 'Received',
			'STATUS': 'Success',
		})
		i = 0
		while True:
			i += 1
			if not ret.has_key('L_TRANSACTIONID%i' % i): break
			if not ret['L_TYPE%i' % i][0] == 'Payment': continue
			yield PaypalTransaction(self, ret, i)

	def get_transaction_details(self, transactionid):
		return self._api_call('GetTransactionDetails', {
			'TRANSACTIONID': transactionid,
		})

	def _dateformat(self, d):
		return d.strftime("%Y-%m-%dT%H:%M:%S")

	def _api_call(self, command, params):
		params.update(self.accessparam)
		params.update({
			'METHOD': command,
		})
		resp = urllib2.urlopen(self.API_ENDPOINT, urlencode(params)).read()
		return parse_qs(resp)


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print "Usage: paypal.py <dsn>"
		sys.exit(1)

	db = psycopg2.connect(sys.argv[1])
	cursor = db.cursor()

	cfg = ConfigParser.ConfigParser()
	cfg.read('paypal.ini')

	synctime = datetime.now()

	for sect in cfg.sections():
		if not cfg.has_option(sect, 'optionid'): continue
		if not cfg.has_option(sect, 'user'): continue

		s = PaypalAPI(cfg.get(sect, 'user'), cfg.get(sect, 'apipass'), cfg.get(sect, 'apisig'))
		cursor.execute("SELECT lastsynced FROM confreg_paymentoption WHERE id=%(id)s", {
			'id': cfg.get(sect, 'optionid'),
		})
		for r in s.get_transaction_list(cursor.fetchall()[0][0]-timedelta(days=3)): #always sync with a little overlap
			if r.already_processed(db): continue
			r.fetch_details()
			r.attempt_match(db)
			r.store(db)
		cursor = db.cursor()
		cursor.execute("UPDATE confreg_paymentoption SET lastsynced=%(st)s WHERE id=%(id)s", {
			'st': synctime,
			'id': cfg.get(sect, 'optionid'),
		})
		db.commit()

