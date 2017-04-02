from django.db import models
from django.contrib.auth.models import User

from postgresqleu.countries.models import Country
from postgresqleu.invoices.models import Invoice

from datetime import date, datetime, timedelta

class Member(models.Model):
	user = models.OneToOneField(User, null=False, blank=False, primary_key=True)
	fullname = models.CharField(max_length=500, null=False, blank=False,
								verbose_name='Full name')
	country = models.ForeignKey(Country, null=False, blank=False)
	listed = models.BooleanField(null=False, blank=False, default=True,
								 verbose_name='Listed in the public membership list')
	paiduntil = models.DateField(null=True, blank=True)
	membersince = models.DateField(null=True, blank=True)

	# If there is a currently active invoice, link to it here so we can
	# easily render the information on the page.
	activeinvoice = models.ForeignKey(Invoice, null=True, blank=True)

	# When a membeship expiry warning was last sent, so we don't keep
	# sending them over and over again
	expiry_warning_sent = models.DateTimeField(null=True, blank=True)

	# WARNING! New fields should most likely be added to the exclude list
	# in MemberForm!!!

	@property
	def expiressoon(self):
		if self.paiduntil:
			if self.paiduntil < date.today() + timedelta(60):
				return True
			else:
				return False
		else:
			return True

	def __unicode__(self):
		return "%s (%s)" % (self.fullname, self.user.username)

class MemberLog(models.Model):
	member = models.ForeignKey(Member, null=False, blank=False)
	timestamp = models.DateTimeField(null=False)
	message = models.TextField(null=False, blank=False)

	def __unicode__(self):
		return "%s: %s" % (self.timestamp, self.message)

class Meeting(models.Model):
	name = models.CharField(max_length=100, null=False, blank=False)
	dateandtime = models.DateTimeField(null=False, blank=False)
	allmembers = models.BooleanField(null=False, blank=False)
	members = models.ManyToManyField(Member, blank=True)
	botname = models.CharField(max_length=50, null=False, blank=False)

	def __unicode__(self):
		return "%s (%s)" % (self.name, self.dateandtime)

	@property
	def joining_active(self):
		if datetime.now() > self.dateandtime-timedelta(hours=4):
			return True
		return False

class MemberMeetingKey(models.Model):
	member = models.ForeignKey(Member, null=False, blank=False)
	meeting = models.ForeignKey(Meeting, null=False, blank=False)
	key = models.CharField(max_length=100, null=False, blank=False)

	class Meta:
		unique_together = (('member', 'meeting'), )
