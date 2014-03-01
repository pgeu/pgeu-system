#!/usr/bin/env python

#
# Generate a badges PDF file
#


import os
import sys
import logging

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from postgresqleu.confreg.models import Conference, ConferenceRegistration
from postgresqleu.confreg.badges import BadgeBuilder

if __name__ == "__main__":
	logging.disable(logging.WARNING)

	if len(sys.argv) != 3:
		print "Usage: generate_badges.py <confname> <output>"
		sys.exit(1)

	conf = Conference.objects.get(urlname=sys.argv[1])
	regs = ConferenceRegistration.objects.filter(conference=conf, payconfirmedat__isnull=False)

	bb = BadgeBuilder(conf,regs)
	bb.render(sys.argv[2])
