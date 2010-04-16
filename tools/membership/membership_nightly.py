#!/usr/bin/env python
#
# This script does nightly batch runs for the membership system. Primarily,
# this means expiring old members.
#
# Copyright (C) 2010, PostgreSQL Europe
#

import sys
import psycopg2

if __name__ == "__main__":
	if len(sys.argv) != 2:
		print "Usage: membership_nightly.py <dsn>"
		sys.exit(1)

	db = psycopg2.connect(sys.argv[1])
	cursor = db.cursor()

	# Write log records for expired members
	cursor.execute("INSERT INTO membership_memberlog (member_id, timestamp, message) SELECT user_id, CURRENT_TIMESTAMP, 'Membership expired' FROM membership_member WHERE paiduntil<CURRENT_DATE")
	cursor.execute("UPDATE membership_member SET membersince=NULL, paiduntil=NULL WHERE paiduntil<CURRENT_DATE")
	
	db.commit()
