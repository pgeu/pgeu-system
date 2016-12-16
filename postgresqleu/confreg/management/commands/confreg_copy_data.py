#
# Copy entries form one conference to another, typically to
# set up a new instance in a series.
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from postgresqleu.confreg.models import Conference
from postgresqleu.confreg.models import RegistrationClass, RegistrationType

class Command(BaseCommand):
	help = 'Copy conference metadata'

	def add_arguments(self, parser):
		parser.add_argument('source', type=str)
		parser.add_argument('dest', type=str)
		parser.add_argument('type', type=str, choices=('regtypes', 'talkslots'))

	def handle(self, *args, **options):
		with transaction.atomic():
			try:
				self.source = Conference.objects.get(urlname=options['source'])
			except Conference.DoesNotExist:
				raise CommandError("Could not find source conference")

			try:
				self.dest = Conference.objects.get(urlname=options['dest'])
			except Conference.DoesNotExist:
				raise CommandError("Could not find destination conference")

			print "Copying from {0} to {1}".format(self.source, self.dest)
			print "------------"

			if options['type'] == 'regtypes':
				if self.dest.registrationclass_set.exists():
					raise CommandError("Destination already has registration classes")
				if self.dest.registrationtype_set.exists():
					raise CommandError("Destination already has registration types")
				self.copy_regclasses(False)
				if self.confirm('Good to copy?'):
					self.copy_regclasses(True)
					print "Done."
			elif options['type'] == 'talkslots':
				raise CommandError("Not implemented yet")
			else:
				# Could not happen, so throw hard exception
				raise CommandError("Invalid type specified")

	def confirm(self, prompt):
		while True:
			s = raw_input(prompt)
			if s and s[0].lower() == 'y':
				return True
			if s and s[0].lower() == 'n':
				return False

	def copy_regclasses(self, actually_copy):
		# First copy any registration classes, and their types
		for c in RegistrationClass.objects.filter(conference=self.source):
			print "Regclass '{0}', color {1}".format(c.regclass, c.badgecolor)
			if actually_copy:
				newc = RegistrationClass(conference=self.dest,
										 regclass=c.regclass,
										 badgecolor=c.badgecolor,
										 badgeforegroundcolor=c.badgeforegroundcolor)
				newc.save()
			else:
				newc = None
			for rt in c.registrationtype_set.all():
				self.copy_regtype(rt, newc, actually_copy)

		# Then copy any registration types that don't have a class
		for rt in self.source.registrationtype_set.filter(regclass__isnull=True):
			if actually_copy:
				self.copy_regtype(rt, None, actually_copy)

	def copy_regtype(self, regtype, destclass, actually_copy):
		print "Regtype {0}, cost {1}, active {2}".format(regtype.regtype, regtype.cost, regtype.active)
		if regtype.days.exists():
			print "WARNING: not copying days value over"
		if regtype.requires_option.exists():
			print "WARNING: not copying required options"

		if not actually_copy:
			return

		rt = RegistrationType(conference=self.dest,
							  regtype=regtype.regtype,
							  regclass=destclass,
							  cost=regtype.cost,
							  active=regtype.active,
							  activeuntil=None,
							  inlist=regtype.inlist,
							  sortkey=regtype.sortkey,
							  specialtype=regtype.specialtype,
							  alertmessage=regtype.alertmessage,
							  upsell_target=regtype.upsell_target,
							  invoice_autocancel_hours=None,
							  )
		rt.save()
