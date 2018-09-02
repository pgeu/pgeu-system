from django.db import models
from postgresqleu.countries.models import Country

class News(models.Model):
	title = models.CharField(max_length=128, blank=False)
	datetime = models.DateTimeField(blank=False)
	summary = models.TextField(blank=False)
	
	def __str__(self):
		return self.title

	@property
	def pretty_date(self):
		return self.datetime.strftime("%d %B %Y")

	class Meta:
		ordering = ['-datetime','title']
		verbose_name_plural = 'News'
