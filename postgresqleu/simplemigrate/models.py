from django.db import models

class AppScript(models.Model):
	app = models.CharField(max_length=32, null=False, blank=False, primary_key=True)
	ver = models.IntegerField(null=False, blank=False, default=0)

	class Meta:
		db_table = '_appscripts'
