from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.http import QueryDict

from postgresqleu.adyen.models import RawNotification, AdyenLog
from postgresqleu.adyen.util import process_raw_adyen_notification


class Command(BaseCommand):
	help = 'Reprocess a raw notification that for some reason failed'

	def add_arguments(self, parser):
		parser.add_argument('id', type=int)

	def handle(self, *args, **options):
		with transaction.atomic():
			try:
				rawnotification = RawNotification.objects.get(pk=options['id'])
			except RawNotification.DoesNotExist:
				raise CommandError("Notification {0} not found.".format(options['id']))

			if rawnotification.confirmed:
				raise CommandError("Notification {0} is already processed.".format(options['id']))

			# Rebuild a POST dictionary with the contents of this request
			POST = QueryDict(rawnotification.contents, "utf8")

			AdyenLog(pspReference=rawnotification.id, message='Reprocessing RAW notification id %s' % rawnotification.id, error=False).save()

			process_raw_adyen_notification(rawnotification, POST)
			self.stdout.write("Completed reprocessing raw notification {0}".format(rawnotification.id))

