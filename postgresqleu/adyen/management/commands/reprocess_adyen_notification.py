from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from postgresqleu.adyen.models import Notification, AdyenLog
from postgresqleu.adyen.util import process_one_notification


class Command(BaseCommand):
	help = 'Reprocess a notification that for some reason failed'

	def add_arguments(self, parser):
		parser.add_argument('pspreference')

	def handle(self, *args, **options):
		with transaction.atomic():
			try:
				notification = Notification.objects.get(pspReference=options['pspreference'])
			except Notification.DoesNotExist:
				raise CommandError("Notification {0} does not exist.".format(options['pspreference']))

			AdyenLog(pspReference=notification.pspReference,
					 message='Reprocessing notification id {0}'.format(notification.id),
					 error=False).save()

			process_one_notification(notification)
			self.stdout.write("Completed reprocessing notification {0}.".format(notification.pspReference))
