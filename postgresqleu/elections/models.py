from django.db import models
from postgresqleu.membership.models import Member

class Election(models.Model):
	name = models.CharField(max_length=100, null=False, blank=False)
	startdate = models.DateField(null=False, blank=False)
	enddate = models.DateField(null=False, blank=False)
	slots = models.IntegerField(null=False, default=1)
	isopen = models.BooleanField(null=False, default=False)
	resultspublic = models.BooleanField(null=False, default=False)

	def __unicode__(self):
		return self.name

class Candidate(models.Model):
	election = models.ForeignKey(Election, null=False, blank=False, on_delete=models.CASCADE)
	name = models.CharField(max_length=100, null=False, blank=False)
	email = models.EmailField(max_length=200, null=False, blank=False)
	presentation = models.TextField(null=False, blank=False)

	def __unicode__(self):
		return "%s (%s)" % (self.name, self.election)

class Vote(models.Model):
	election = models.ForeignKey(Election, null=False, blank=False, on_delete=models.CASCADE)
	voter = models.ForeignKey(Member, null=False, blank=False, on_delete=models.CASCADE)
	candidate = models.ForeignKey(Candidate, null=False, blank=False, on_delete=models.CASCADE)
	score = models.IntegerField(null=False, blank=False)
