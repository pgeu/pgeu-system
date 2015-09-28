#!/usr/bin/env python

#
# Send reminders to speakers and attendees that have their
# sessions or registration in an unconfirmed state.
#
# Intended to run on a weekly or so basis, not more often
# than that.
#

import sys
import os
from cStringIO import StringIO
from datetime import datetime, timedelta

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction
from django.template import Context
from django.template.loader import get_template

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.models import Conference, Speaker, ConferenceSession

def remind_pending_speakers(whatstr, conference):
	# Remind speakers that are in pending status. But only the ones
	# where we've actually sent the status emails, meaning the
	# lastsent is the same as the current.
	speakers = Speaker.objects.filter(conferencesession__conference=conference,
									  conferencesession__status=3,
									  conferencesession__lastnotifiedstatus=3,
									  conferencesession__lastnotifiedtime__lt=datetime.now()-timedelta(days=7)).distinct()
	if speakers:
		whatstr.write("Found {0} unconfirmed talks:\n".format(len(speakers)))
		template = get_template('confreg/mail/speaker_remind_confirm.txt')

		for speaker in speakers:
			sessions = speaker.conferencesession_set.filter(conference=conference, status=3)
			for s in sessions:
				s.lastnotifiedtime = datetime.now()
				s.save()

			send_simple_mail(conference.contactaddr,
							 speaker.user.email,
							 "Your submissions to {0}".format(conference),
							 template.render(Context({
								 'conference': conference,
								 'sessions': sessions,
								 'SITEBASE': settings.SITEBASE_SSL,
							 })),
							 sendername = conference.conferencename,
							 receivername = speaker.fullname,
						 )

			whatstr.write("Reminded speaker {0} to confirm {1} talks\n".format(speaker, len(sessions)))

		whatstr.write("\n\n")


def remind_unregistered_speakers(whatstr, conference):
	# Get speakers that are approved but not registered
	speakers = list(Speaker.objects.raw("SELECT s.* FROM confreg_speaker s WHERE EXISTS (SELECT 1 FROM confreg_conferencesession sess INNER JOIN confreg_conferencesession_speaker css ON css.conferencesession_id=sess.id WHERE sess.conference_id=%s AND css.speaker_id=s.id AND sess.status=1 AND sess.lastnotifiedtime<%s) AND NOT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%s AND r.attendee_id=s.user_id AND r.payconfirmedat IS NOT NULL)",
										[conference.id, datetime.now()-timedelta(days=7), conference.id]))
	if speakers:
		whatstr.write("Found {0} unregistered speakers:\n".format(len(speakers)))
		template = get_template('confreg/mail/speaker_remind_register.txt')
		for speaker in speakers:
			# Update the last notified date on all sessions that are in
			# status approved, to make sure we don't send a second
			# reminder tomorrow.
			ConferenceSession.objects.filter(conference=conference,
											 speaker=speaker,
											 status=1
			).update(
				lastnotifiedtime=datetime.now()
			)

			send_simple_mail(conference.contactaddr,
							 speaker.user.email,
							 "Your registration to {0}".format(conference),
							 template.render(Context({
								 'conference': conference,
								 'SITEBASE': settings.SITEBASE_SSL,
							 })),
							 sendername = conference.conferencename,
							 receivername = speaker.fullname,
						 )

			whatstr.write("Reminded speaker {0} to register\n".format(speaker))



if __name__ == "__main__":
	for conference in Conference.objects.filter(active=True):
		# One transaction for each open conference that has registration
		# open. If registration isn't open then there is nowhere to
		# register, so don't even try.
		with transaction.commit_on_success():
			whatstr = StringIO()

			if conference.registrationtype_set.filter(specialtype='spk').exists():
				remind_pending_speakers(whatstr, conference)
				remind_unregistered_speakers(whatstr, conference)

			# Do we need to send a central mail?
			if whatstr.tell():
				# More than one character, so we have done something. Send
				# a report to the conference organizers about it.
				send_simple_mail(conference.contactaddr,
								 conference.contactaddr,
								 "Reminders sent",
								 whatstr.getvalue(),
								 sendername = conference.conferencename,
								 receivername = conference.conferencename,
								 )
