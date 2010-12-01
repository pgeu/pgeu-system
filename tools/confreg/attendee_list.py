#!/usr/bin/env python
#
# Tool to generate an attendee-list for a conference,
# for ticking off at registration etc. Also includes
# support for generating attendee lists/buyer list for
# additional options.
#

import sys
import os
import psycopg2
import psycopg2.extensions

from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus.tables import Table, TableStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, landscape

def Usage():
	print "Usage: attendee_list.py <connectionstring> <conferenceshortname> [additional option name/id]"
	sys.exit(1)

if __name__ == "__main__":
	if len(sys.argv) != 3 and len(sys.argv) != 4:
		Usage()
	connstr = sys.argv[1]
	shortname = sys.argv[2]
	if len(sys.argv) == 4:
		addopt = sys.argv[3]
	else:
		addopt = None

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	db = psycopg2.connect(connstr)
	curs = db.cursor()
	curs.execute("SELECT id,conferencename,autoapprove FROM confreg_conference WHERE urlname=%(url)s", {'url': shortname})
	try:
		r = curs.fetchall()[0]
		confid = r[0]
		confname = r[1]
		autoapprove = r[2]
	except:
		print "Could not find conference in database!"
		sys.exit(1)

	if not addopt:
		# Conference attendee list

		curs.execute("SELECT lastname, firstname, company,regtype || COALESCE(rtrim(E'\n'||(SELECT textcat_all(ao.name || E'\n') FROM confreg_conferenceadditionaloption ao INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceadditionaloption_id=ao.id WHERE rao.conferenceregistration_id=r.id),E'\n'),'') AS regtype, shirtsize, payconfirmedat, payconfirmedby, '' FROM confreg_conferenceregistration r INNER JOIN confreg_registrationtype rt ON r.regtype_id=rt.id LEFT JOIN confreg_shirtsize s ON s.id=r.shirtsize_id WHERE r.conference_id=%(confid)s ORDER BY lower(lastname), lower(firstname)", {'confid': confid})
		headline = ["Last name","First name", "Company", "Registration type", "Shirt", "Paid at", "Confirmed by", "Arrived"]
		colwidths = [5*cm, 5*cm, 4*cm, 6*cm, 1.2*cm, 2.5*cm, 3*cm, 2.5*cm]
		filename = shortname
		title = "Attendee list: %s" % confname
	else:
		# Additional option attendees list - much less detail, assume
		# paid etc etc
		if not addopt.isdigit():
			# Look up by name
			curs.execute("SELECT id FROM confreg_conferenceadditionaloption WHERE conference_id=%(confid)s AND name=%(name)s", {
					'confid': confid,
					'name': addopt,
					})
			r = curs.fetchall()
			if len(r) != 1:
				print "Could not find additional option '%s' for this conference" % addopt
				sys.exit(1)
			addoptid = int(r[0][0])
		else:
			# Verify this id is correct
			curs.execute("SELECT conference_id,name FROM confreg_conferenceadditionaloption WHERE id=%(id)s", {'id': int(addopt)})
			r = curs.fetchall()
			if len(r) != 1:
				print "Could not find additional option with id %s" % addoptid
				sys.exit(1)
			if int(r[0][0]) != confid:
				print "Additional option with id %s does not belong to this conference" % addopt
				sys.exit(1)
			addoptid = int(addopt)
			addopt = r[0][1]

		# Now get the list for this option
		curs.execute("SELECT lastname, firstname, company, '' FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration_additionaloptions rao ON r.id=rao.conferenceregistration_id WHERE r.conference_id=%(confid)s AND rao.conferenceadditionaloption_id=%(id)s ORDER BY lower(lastname), lower(firstname)", {
				'confid': confid,
				'id': addoptid,
				})
		headline = ["Last name","First name", "Company", "Arrived"]
		colwidths = [8*cm, 8*cm, 8*cm, 3*cm]
		filename = "%s_%s" % (shortname, addoptid)
		title = "Attendee list: %s" % addopt

	rows = curs.fetchall()
	rows.insert(0, headline)

	doc = SimpleDocTemplate("%s.pdf" % filename, pagesize=landscape(A4))

	styles=getSampleStyleSheet()
	t = Table([[Paragraph(unicode(s).replace('\n','<br/>'),styles['Normal']) for s in r] for r in rows],
			  colwidths,
			  repeatRows=1)

	t.setStyle(TableStyle([
				('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
				('LINEBELOW',(0,0),(-1,0), 2, colors.black),
				('GRID', (0,0), (-1, -1), 1, colors.black),
				]))

	doc.build([Paragraph(title,styles['title']),
			t])
