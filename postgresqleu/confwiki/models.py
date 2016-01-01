from django.db import models
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

from postgresqleu.confreg.models import Conference, ConferenceRegistration
from postgresqleu.confreg.models import RegistrationType

from postgresqleu.util.diffablemodel import DiffableModel

class Wikipage(models.Model, DiffableModel):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	url = models.CharField(max_length=100, null=False, blank=False, validators=[
		RegexValidator(regex='^[a-zA-Z0-9_-]+$',
					   message='Invalid character in urlname. Only alphanumerical, underscore and dash are allowed.'),])
	title = models.CharField(max_length=100, null=False, blank=False)
	author = models.ForeignKey(ConferenceRegistration, null=False, blank=False)
	publishedat = models.DateTimeField(null=False, blank=False, auto_now=True)
	contents = models.TextField(null=False, blank=False)

	# Can the public (=anybody registered) view/edit this?
	publicview = models.BooleanField(null=False, blank=False, default=False,
									 verbose_name="Public view",
									 help_text="Can all confirmed attendees see this page?")
	publicedit = models.BooleanField(null=False, blank=False, default=False,
									 verbose_name="Public edit",
									 help_text="Can all confirmed attendees edit this page?")

	# Do we allow anybody to view the history (we always track history,
	# this is only about it being viewable to non-admins)
	history = models.BooleanField(null=False, blank=False, default=True, help_text="Can users view the history?")

	# Several rounds of permissions. Can be done smarter? Maybe...
	viewer_regtype = models.ManyToManyField(RegistrationType, blank=True, related_name='viewer_regtypes', verbose_name="Viewer registration types")
	editor_regtype = models.ManyToManyField(RegistrationType, blank=True, related_name='editor_regtypes', verbose_name="Editor registration types")
	viewer_attendee = models.ManyToManyField(ConferenceRegistration, blank=True, related_name='viewer_attendees', verbose_name="Viewer attendees")
	editor_attendee = models.ManyToManyField(ConferenceRegistration, blank=True, related_name='editor_attendees', verbose_name="Editor attendees")

	class Meta:
		unique_together = [
			('conference', 'url', )
		]
		ordering = ('title', )

	def __unicode__(self):
		return "{0} ({1})".format(self.url, self.title)

	map_manytomany_for_diff = {
		'viewer_regtype': 'viewer_regtypes',
		'editor_regtype': 'editor_regtypes',
		'viewer_attendee': 'viewer_attendees',
		'editor_attendee': 'editor_attendees',
		}

	@property
	def viewer_regtypes(self):
		return ", ".join([r.regtype for r in self.viewer_regtype.all()])

	@property
	def editor_regtypes(self):
		return ", ".join([r.regtype for r in self.editor_regtype.all()])

	@property
	def viewer_attendees(self):
		return ", ".join([r.fullname for r in self.viewer_attendee.all()])

	@property
	def editor_attendees(self):
		return ", ".join([r.fullname for r in self.editor_attendee.all()])

# When a page is edited, the old version is copied over to the history. A page that has
# never been edited has no history entry. Permission changes are not tracked.
class WikipageHistory(models.Model):
	page = models.ForeignKey(Wikipage, null=False, blank=False, db_index=True)
	author = models.ForeignKey(ConferenceRegistration, null=False, blank=False)
	publishedat = models.DateTimeField(null=False, blank=False)
	contents = models.TextField(null=False, blank=False)

	class Meta:
		ordering = ('-publishedat',)
		unique_together = (
			('page', 'publishedat',)
		)

# Subscribers to changes of wikipages
class WikipageSubscriber(models.Model):
	page = models.ForeignKey(Wikipage, null=False, blank=False, db_index=True)
	subscriber = models.ForeignKey(ConferenceRegistration, null=False, blank=False)


def validate_options(value):
	pieces = [v.strip() for v in value.split(',')]
	if len(pieces) < 2:
		raise ValidationError("At least two options must be given")
	for v in pieces:
		if len(v) < 1:
			raise ValidationError("Empty options are not allowed")
		if len(v) > 100:
			raise ValidationError("Options must be less than 100 characters each")


# Signups - attendees can sign up for events
class Signup(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	author = models.ForeignKey(ConferenceRegistration, null=False, blank=False)
	title = models.CharField(max_length=100, null=False, blank=False)
	intro = models.TextField(null=False, blank=False)
	deadline = models.DateTimeField(null=True, blank=True)
	maxsignups = models.IntegerField(null=False, blank=False, default=-1)
	options = models.CharField(max_length=1000, null=False, blank=True, help_text="Comma separated list of options to choose.", validators=[validate_options,])

	public = models.BooleanField(null=False, blank=False, default=False, help_text="All attendees can sign up")
	visible = models.BooleanField(null=False, blank=False, default=False, help_text="Show who have signed up to all invited attendees")
	regtypes = models.ManyToManyField(RegistrationType, blank=True, verbose_name="Available to registration types", related_name="user_regtypes")
	attendees = models.ManyToManyField(ConferenceRegistration, blank=True, verbose_name="Available to attendees", related_name="user_attendees")

	class Meta:
		ordering = ('deadline', 'title', )

class AttendeeSignup(models.Model):
	signup = models.ForeignKey(Signup, null=False, blank=False)
	attendee = models.ForeignKey(ConferenceRegistration, null=False, blank=False)
	choice = models.CharField(max_length=100, null=False, blank=True)
	saved = models.DateTimeField(null=False, blank=False, auto_now=True)

	class Meta:
		unique_together = (
			('signup', 'attendee',),
		)
