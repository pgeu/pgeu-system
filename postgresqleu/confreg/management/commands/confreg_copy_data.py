#
# Copy entries form one conference to another, typically to
# set up a new instance in a series.
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from datetime import timedelta

from postgresqleu.confreg.models import Conference
from postgresqleu.confreg.models import RegistrationClass, RegistrationType
from postgresqleu.confreg.models import ConferenceSessionScheduleSlot
from postgresqleu.confreg.models import ConferenceFeedbackQuestion
from postgresqleu.confreg.models import Track, ConferenceSession

class Command(BaseCommand):
	help = 'Copy conference metadata'

	def add_arguments(self, parser):
		parser.add_argument('source', type=str)
		parser.add_argument('dest', type=str)
		parser.add_argument('type', type=str, choices=('regtypes', 'talkslots', 'feedback', 'sessions'))
		parser.add_argument('--sourcetrack', type=str)
		parser.add_argument('--desttrack', type=str)

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
				if self.dest.conferencesessionscheduleslot_set.exists():
					raise CommandError("Destination already has talk slots!")
				num = self.source.conferencesessionscheduleslot_set.count()
				if num == 0:
					raise CommandError("Source does not have any talk slots!")

				# How many days to move forward
				days = (self.dest.startdate-self.source.startdate).days
				print "First talk slot will be: {0}".format(self.source.conferencesessionscheduleslot_set.order_by('starttime')[0].starttime + timedelta(days=days))
				print "Last talk slot will be: {0}".format(self.source.conferencesessionscheduleslot_set.order_by('-starttime')[0].starttime + timedelta(days=days))

				if self.confirm('Proceed to copy {0} talk slots, forwading {1} days?'.format(num, days)):
					for s in self.source.conferencesessionscheduleslot_set.order_by('starttime'):
						ConferenceSessionScheduleSlot(conference=self.dest,
													  starttime=s.starttime + timedelta(days=days),
													  endtime=s.endtime + timedelta(days=days),
													  ).save()
			elif options['type'] == 'feedback':
				if self.dest.conferencefeedbackquestion_set.exists():
					raise CommandError("Destination already has feedback questions!")
				num = self.source.conferencefeedbackquestion_set.count()
				if self.confirm("Proceed to copy {0} feedback questions, replacing conference name and location?".format(num)):
					for q in self.source.conferencefeedbackquestion_set.order_by('sortkey'):
						ConferenceFeedbackQuestion(
							conference=self.dest,
							question=q.question.replace(self.source.conferencename, self.dest.conferencename).replace(self.source.location, self.dest.location),
							isfreetext=q.isfreetext,
							textchoices=q.textchoices,
							sortkey=q.sortkey,
							newfieldset=q.newfieldset,
						).save()
			elif options['type'] == 'sessions':
				if not options['sourcetrack'] or not options['desttrack']:
					raise CommandError("Track must be given when copying sessions")
				try:
					self.sourcetrack = Track.objects.get(conference=self.source, trackname=options['sourcetrack'])
				except Track.DoesNotExist:
					raise CommandError("Source track '{0}' does not exist.".format(options['sourcetrack']))
				try:
					self.desttrack = Track.objects.get(conference=self.dest, trackname=options['desttrack'])
				except Track.DoesNotExist:
					raise CommandError("Destination track '{0}' does not exist.".format(options['desttrack']))
				sessions = list(ConferenceSession.objects.filter(conference=self.source, track=self.sourcetrack))
				if len(sessions) == 0:
					raise CommandError("No sessions found.")
				for s in sessions:
					print "Copying session %s" % s.title
					n = ConferenceSession(conference=self.dest,
										  track=self.desttrack,
										  title=s.title,
										  abstract=s.abstract,
										  skill_level=s.skill_level,
										  status=0,
										  initialsubmit=s.initialsubmit,
										  submissionnote=s.submissionnote,
					)
					n.save()
					n.speaker = s.speaker.all()
				if not self.confirm('Copied {0} sessions. Proceed to commit?'.format(len(sessions))):
					raise CommandError("Aborting")
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
