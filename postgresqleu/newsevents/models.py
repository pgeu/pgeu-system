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

class Event(models.Model):
	title = models.CharField(max_length=128, blank=False)
	startdate = models.DateField(blank=False)
	enddate = models.DateField(blank=False)
	city = models.CharField(max_length=128, blank=False)
	state = models.CharField(max_length=8, blank=True)
	country = models.ForeignKey(Country, null=False)
	summary = models.TextField(blank=False)

	def __str__(self):
		return self.title

	@property
	def full_location(self):
		if self.state:
			return "%s, %s, %s" % (self.city, self.state, self.country)
		return "%s, %s" % (self.city, self.country)

	@property
	def pretty_date(self):
		if self.startdate.year == self.enddate.year and self.startdate.month == self.enddate.month:
			return "%s-%s %s, %s" % (self.startdate.day, self.enddate.day, self.startdate.strftime("%B"), self.startdate.year)
		return "Don't know how to format this yet"

	class Meta:
		ordering = ['startdate','title']

