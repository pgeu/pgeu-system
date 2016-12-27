from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.http import QueryDict

from postgresqleu.trustlypayment.models import TrustlyNotification, TrustlyLog
from postgresqleu.trustlypayment.util import Trustly


class Command(BaseCommand):
	help = 'Reprocess a notification that for some reason failed'

	def add_arguments(self, parser):
		parser.add_argument('id')

	def handle(self, *args, **options):
		with transaction.atomic():
			try:
				notification = TrustlyNotification.objects.get(id=options['id'])
			except TrustlyNotification.DoesNotExist:
				raise CommandError("Notification {0} does not exist.".format(options['id']))

			TrustlyLog(message="Reprocessing notification {0}".format(notification.id)).save()

			t = Trustly()
			result = t.process_notification(notification)
		if not result:
			raise CommandError("Reprocessing failed, see log!")

		self.stdout.write("Completed reprocessing notification {0}.".format(notification.id))
