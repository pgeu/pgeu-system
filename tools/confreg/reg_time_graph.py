#!/usr/bin/env python
#
# Tool to generate a graph of when people did register
#
import sys
import psycopg2
import psycopg2.extensions
from pygooglechart import GroupedVerticalBarChart, Axis



def Usage():
	print "Usage: reg_time_graph.py <connectionstring> <conferenceshortname>"
	sys.exit(1)

if __name__ == "__main__":
	if len(sys.argv) != 3:
		Usage()
	connstr = sys.argv[1]
	confname = sys.argv[2]

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	db = psycopg2.connect(connstr)
	curs = db.cursor()
	curs.execute("SELECT id,conferencename FROM confreg_conference WHERE urlname=%(url)s", {'url': confname})
	try:
		r = curs.fetchall()[0]
		confid = r[0]
		confname = r[1]
	except:
		print "Could not find conference in database!"
		sys.exit(1)

	curs.execute("""
SELECT date_trunc('week', payconfirmedat),sum(c) FROM (
SELECT payconfirmedat,count(*) AS c FROM confreg_conferenceregistration
WHERE conference_id=%(id)s AND payconfirmedat IS NOT NULL GROUP BY payconfirmedat
UNION ALL
SELECT (
	SELECT min(payconfirmedat) FROM confreg_conferenceregistration WHERE conference_id=%(id)s)+
   CAST(g || ' days' AS interval),
  0
 FROM generate_series(0, (SELECT max(payconfirmedat)-min(payconfirmedat) FROM confreg_conferenceregistration WHERE conference_id=%(id)s)) g(g)
) x GROUP BY date_trunc('week', payconfirmedat)
ORDER BY 1
""" % {
			'id': confid,
			})
	rows = curs.fetchall()
	num = len(rows)
	
	chart = GroupedVerticalBarChart(num * 40,300)
	chart.set_bar_width(30)
	chart.set_bar_spacing(10)
	chart.set_title("Registrations by week for %s" % confname)
	chart.add_data([float(r[1]) for r in rows])
	chart.set_axis_labels(Axis.BOTTOM, 
			[r[0].strftime("%d %b") for r in rows])

	chart.download('%s.png' % confid)
	print "Done, se %s.png" % confid
