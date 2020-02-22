#
# Send reminders to speakers and attendees that have their
# sessions or registration in an unconfirmed state.
#
# Intended to run on a daily basis, as each reminder has it's
# own check for when the user was last notified.
#
from django.core.management.base import BaseCommand
from django.db import transaction

from io import StringIO
from datetime import datetime, timedelta, time

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.models import Conference, Speaker, ConferenceSession
from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.confreg.util import send_conference_mail


class Command(BaseCommand):
    help = 'Send conference reminders'

    class ScheduledJob:
        scheduled_times = [time(5, 52), ]
        internal = True

    def handle(self, *args, **options):
        for conference in Conference.objects.filter(active=True):
            # One transaction for each open conference that has registration
            # open. If registration isn't open then there is nowhere to
            # register, so don't even try.
            with transaction.atomic():
                whatstr = StringIO()

                if conference.registrationtype_set.filter(specialtype__in=('spk', 'spkr')).exists():
                    self.remind_pending_speakers(whatstr, conference)
                    self.remind_unregistered_speakers(whatstr, conference)

                self.remind_pending_registrations(whatstr, conference)
                self.remind_pending_multiregs(whatstr, conference)

                # Do we need to send a central mail?
                if whatstr.tell():
                    # More than one character, so we have done something. Send
                    # a report to the conference organizers about it.
                    send_simple_mail(conference.notifyaddr,
                                     conference.notifyaddr,
                                     "Reminders sent",
                                     whatstr.getvalue(),
                                     sendername=conference.conferencename,
                                     receivername=conference.conferencename,
                                     )

        for conference in Conference.objects.filter(callforpapersopen=True):
            # One transaction for each conference with call for papers open, to send reminders
            # for things related to the cfp.
            with transaction.atomic():
                whatstr = StringIO()
                self.remind_empty_submissions(whatstr, conference)
                self.remind_empty_speakers(whatstr, conference)

                if whatstr.tell():
                    send_simple_mail(conference.notifyaddr,
                                     conference.notifyaddr,
                                     "CfP reminders sent",
                                     whatstr.getvalue(),
                                     sendername=conference.conferencename,
                                     receivername=conference.conferencename,
                                 )

    def remind_pending_speakers(self, whatstr, conference):
        # Remind speakers that are in pending status. But only the ones
        # where we've actually sent the status emails, meaning the
        # lastsent is the same as the current.
        speakers = Speaker.objects.filter(conferencesession__conference=conference,
                                          conferencesession__status=3,
                                          conferencesession__lastnotifiedstatus=3,
                                          conferencesession__lastnotifiedtime__lt=datetime.now() - timedelta(days=7)).distinct()
        if speakers:
            whatstr.write("Found {0} unconfirmed talks:\n".format(len(speakers)))

            for speaker in speakers:
                sessions = speaker.conferencesession_set.filter(conference=conference, status=3)
                for s in sessions:
                    s.lastnotifiedtime = datetime.now()
                    s.save()

                send_conference_mail(conference,
                                     speaker.user.email,
                                     "Your submissions".format(conference),
                                     'confreg/mail/speaker_remind_confirm.txt',
                                     {
                                         'conference': conference,
                                         'sessions': sessions,
                                     },
                                     receivername=speaker.fullname,
                )

                whatstr.write("Reminded speaker {0} to confirm {1} talks\n".format(speaker, len(sessions)))

            whatstr.write("\n\n")

    def remind_unregistered_speakers(self, whatstr, conference):
        # Get speakers that are approved but not registered
        speakers = list(Speaker.objects.raw("SELECT s.* FROM confreg_speaker s WHERE EXISTS (SELECT 1 FROM confreg_conferencesession sess INNER JOIN confreg_conferencesession_speaker css ON css.conferencesession_id=sess.id WHERE sess.conference_id=%s AND css.speaker_id=s.id AND sess.status=1 and sess.lastnotifiedstatus=1 AND sess.lastnotifiedtime<%s) AND NOT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%s AND r.attendee_id=s.user_id AND r.payconfirmedat IS NOT NULL)",
                                            [conference.id, datetime.now() - timedelta(days=7), conference.id]))
        if speakers:
            whatstr.write("Found {0} unregistered speakers:\n".format(len(speakers)))
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

                send_conference_mail(conference,
                                     speaker.user.email,
                                     "Your registration".format(conference),
                                     'confreg/mail/speaker_remind_register.txt',
                                     {
                                         'conference': conference,
                                     },
                                     receivername=speaker.fullname,
                )

                whatstr.write("Reminded speaker {0} to register\n".format(speaker))

            whatstr.write("\n\n")

    def remind_pending_registrations(self, whatstr, conference):
        # Get registrations made which have no invoice, no bulk registration,
        # and are not completed. We look at registrations created more than 5
        # days ago and also unmodified for 5 days. This is intentionally not 7
        # days in order to "rotate the day of week" the reminders go out on.
        # Only send reminders if attendee has a value, meaning we don't send
        # reminders to registrations that are managed by somebody else.
        regs = ConferenceRegistration.objects.filter(conference=conference,
                                                     conference__active=True,
                                                     conference__enddate__gt=datetime.now(),
                                                     attendee__isnull=False,
                                                     payconfirmedat__isnull=True,
                                                     invoice__isnull=True,
                                                     bulkpayment__isnull=True,
                                                     registrationwaitlistentry__isnull=True,
                                                     created__lt=datetime.now() - timedelta(days=5),
                                                     lastmodified__lt=datetime.now() - timedelta(days=5))

        if regs:
            whatstr.write("Found {0} unconfirmed registrations that are stalled:\n".format(len(regs)))
            for reg in regs:
                send_conference_mail(conference,
                                     reg.email,
                                     "Your registration".format(conference),
                                     'confreg/mail/attendee_stalled_registration.txt',
                                     {
                                         'conference': conference,
                                         'reg': reg,
                                     },
                                     receivername=reg.fullname,
                )
                reg.lastmodified = datetime.now()
                reg.save()

                whatstr.write("Reminded attendee {0} that their registration is not confirmed\n".format(reg.fullname))

            whatstr.write("\n\n")

    def remind_pending_multiregs(self, whatstr, conference):
        # Reminde owners of "multiregs" that have not been completed. Basic rules
        # are the same as remind_pending_registrations(), but we only consider
        # those that are managed by somebody else.
        regs = ConferenceRegistration.objects.filter(conference=conference,
                                                     conference__active=True,
                                                     conference__enddate__gt=datetime.now(),
                                                     attendee__isnull=True,
                                                     registrator__isnull=False,
                                                     payconfirmedat__isnull=True,
                                                     invoice__isnull=True,
                                                     bulkpayment__isnull=True,
                                                     registrationwaitlistentry__isnull=True,
                                                     created__lt=datetime.now() - timedelta(days=5),
                                                     lastmodified__lt=datetime.now() - timedelta(days=5))

        if regs:
            multiregs = set([r.registrator for r in regs])

            whatstr.write("Found {0} unconfirmed multiregistrations that are stalled:\n".format(len(multiregs)))

            for r in multiregs:
                send_conference_mail(conference,
                                     r.email,
                                     "Your registrations".format(conference),
                                     'confreg/mail/multireg_stalled_registration.txt',
                                     {
                                         'conference': conference,
                                         'registrator': r,
                                     },
                                     receivername="{0} {1}".format(r.first_name, r.last_name),
                )

                whatstr.write("Reminded user {0} ({1}) that their multi-registration is not confirmed\n".format(r.username, r.email))

            whatstr.write("\n\n")

            # Separately mark each part of the multireg as touched
            for reg in regs:
                reg.lastmodified = datetime.now()
                reg.save()

    def remind_empty_submissions(self, whatstr, conference):
        # Get all sessions with empty abstract (they forgot to hit save), if they have not been touched in
        # 3 days (this will also make the reminder show up every 3 days, and not every day, since we touch
        # the lastmodified timestemp when a reminder is sent).

        for sess in conference.conferencesession_set.filter(abstract='',
                                                            status=0,
                                                            lastmodified__lt=datetime.now() - timedelta(days=3)):
            for spk in sess.speaker.all():
                send_conference_mail(conference,
                                     spk.email,
                                     "Your submission".format(conference),
                                     'confreg/mail/speaker_empty_submission.txt',
                                     {
                                         'conference': conference,
                                         'session': sess,
                                     },
                                     receivername=spk.name,
                )
                whatstr.write("Reminded speaker {0} that they have made an empty submission\n".format(spk.name))
            sess.lastmodified = datetime.now()
            sess.save()

    def remind_empty_speakers(self, whatstr, conference):
        # Get all the speakers with an active submission to this conference
        # but no bio included, if they have not been touched in  3 days.

        speakers = Speaker.objects.filter(conferencesession__conference=conference,
                                          conferencesession__status=0,
                                          lastmodified__lt=datetime.now() - timedelta(days=3),
                                          abstract='',
                                      ).distinct()

        for spk in speakers:
            send_conference_mail(conference,
                                 spk.email,
                                 "Your submission".format(conference),
                                 'confreg/mail/speaker_empty_profile.txt',
                                 {
                                     'conference': conference,
                                     'speaker': spk,
                                 },
                                 receivername=spk.name,
            )
            spk.lastmodified = datetime.now()
            spk.save()
            whatstr.write("Reminded speaker {0} that their profile is empty\n".format(spk.name))
