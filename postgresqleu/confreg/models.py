#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.db import models
from django.db.models import Q
from django.db.models.expressions import F
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils.dateformat import DateFormat
from django.contrib.postgres.fields import DateTimeRangeField

from postgresqleu.util.validators import validate_lowercase
from postgresqleu.util.forms import ChoiceArrayField

from postgresqleu.confreg.dbimage import SpeakerImageStorage

import datetime
import pytz
from decimal import Decimal

from postgresqleu.countries.models import Country
from postgresqleu.invoices.models import Invoice, VatRate
from regtypes import special_reg_types

SKILL_CHOICES = (
	(0, "Beginner"),
	(1, "Intermediate"),
	(2, "Advanced"),
)

STATUS_CHOICES = (
	(0, "Submitted"),
	(1, "Approved"),
	(2, "Rejected"),
	(3, "Pending"), # Approved, but not confirmed
	(4, "Reserve"), # Reserve list
)
STATUS_CHOICES_LONG = (
	(0, "Submitted, not processed yet"),
	(1, "Approved and confirmed"),
	(2, "Rejected"),
	(3, "Pending speaker confirmation"), # Approved, but not confirmed
	(4, "Reserve-listed in case of cancels/changes"), # Reserve list
)
def get_status_string(val):
	return (t for v,t in STATUS_CHOICES if v==val).next()
def get_status_string_long(val):
	return (t for v,t in STATUS_CHOICES_LONG if v==val).next()

valid_status_transitions = {
	0: {3: 'Talk approved', 2: 'Talk is rejected', 4: 'Talk added to reserve list'},
	1: {2: 'Talk withdrawn', },
	2: {0: 'Talk processing reset', },
	3: {0: 'Talk unapproved', 1: 'Speaker confirms', 2: 'Speaker declines'},
	4: {1: 'Last-minute reservelist', 3: 'Activated from reservelist' },
}

def color_validator(value):
	if not value.startswith('#'):
		raise ValidationError('Color values must start with #')
	if len(value) != 7:
		raise ValidationError('Color values must be # + 7 characters')
	for n in range(0,3):
		try:
			int(value[n*2+1:n*2+2+1], 16)
		except ValueError:
			raise ValidationError('Invalid value in color specification')

class ConferenceSeries(models.Model):
	name = models.CharField(max_length=64, blank=False, null=False)

	def __unicode__(self):
		return self.name

class ConferenceSeriesOptOut(models.Model):
	# Users opting out of communications about a specific conference
	series = models.ForeignKey(ConferenceSeries, null=False, blank=False)
	user = models.ForeignKey(User, null=False, blank=False)

	class Meta:
		unique_together = (
			('user', 'series'),
		)

class GlobalOptOut(models.Model):
	# Users who are opting out of *all* future communications
	user = models.OneToOneField(User, null=False, blank=False, primary_key=True)


class Conference(models.Model):
	urlname = models.CharField(max_length=32, blank=False, null=False, unique=True, validators=[validate_lowercase,])
	conferencename = models.CharField(max_length=64, blank=False, null=False)
	startdate = models.DateField(blank=False, null=False)
	enddate = models.DateField(blank=False, null=False)
	location = models.CharField(max_length=128, blank=False, null=False)
	timediff = models.IntegerField(null=False, blank=False, default=0)
	contactaddr = models.EmailField(blank=False,null=False)
	sponsoraddr = models.EmailField(blank=False,null=False)
	active = models.BooleanField(blank=False,null=False,default=False, verbose_name="Registration open")
	callforpapersopen = models.BooleanField(blank=False,null=False,default=False, verbose_name="Call for papers open")
	callforsponsorsopen = models.BooleanField(blank=False,null=False,default=False, verbose_name="Call for sponsors open")
	feedbackopen = models.BooleanField(blank=False,null=False,default=False, verbose_name="Session feedback open")
	conferencefeedbackopen = models.BooleanField(blank=False,null=False,default=False, verbose_name="Conference feedback open")
	scheduleactive = models.BooleanField(blank=False,null=False,default=False,verbose_name="Schedule publishing active")
	sessionsactive = models.BooleanField(blank=False,null=False,default=False,verbose_name="Session list publishing active")
	schedulewidth = models.IntegerField(blank=False, default=600, null=False, verbose_name="Width of HTML schedule")
	pixelsperminute = models.FloatField(blank=False, default=1.5, null=False, verbose_name="Vertical pixels per minute")
	confurl = models.CharField(max_length=128, blank=False, null=False, validators=[validate_lowercase,])
	listadminurl = models.CharField(max_length=128, blank=True, null=False)
	listadminpwd = models.CharField(max_length=128, blank=True, null=False)
	speakerlistadminurl = models.CharField(max_length=128, blank=True, null=False)
	speakerlistadminpwd = models.CharField(max_length=128, blank=True, null=False)
	twittersync_active = models.BooleanField(null=False, default=False)
	twitter_user = models.CharField(max_length=32, blank=True, null=False)
	twitter_attendeelist = models.CharField(max_length=32, blank=True, null=False)
	twitter_speakerlist = models.CharField(max_length=32, blank=True, null=False)
	twitter_sponsorlist = models.CharField(max_length=32, blank=True, null=False)
	twitter_token = models.CharField(max_length=128, blank=True, null=False)
	twitter_secret = models.CharField(max_length=128, blank=True, null=False)

	administrators = models.ManyToManyField(User, blank=True)
	testers = models.ManyToManyField(User, blank=True, related_name="testers_set", help_text="Users who can bypass the '<function> is open' check and access pages before they're open, in order to test")
	talkvoters = models.ManyToManyField(User, blank=True, related_name="talkvoters_set", help_text="Users who can view talks pre-approval, vote on the talks, and leave comments")
	staff = models.ManyToManyField(User, blank=True, related_name="staff_set", help_text="Users who can register as staff")
	volunteers = models.ManyToManyField('ConferenceRegistration', blank=True, related_name="volunteers_set", help_text="Users who volunteer")
	asktshirt = models.BooleanField(blank=False, null=False, default=True, verbose_name="Field: t-shirt", help_text="Include field for T-shirt size")
	askfood = models.BooleanField(blank=False, null=False, default=True, verbose_name="Field: dietary", help_text="Include field for dietary needs")
	asktwitter = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: twitter name", help_text="Include field for twitter name")
	asknick = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: nick", help_text="Include field for nick")
	askshareemail = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: share email", help_text="Include field for sharing email with sponsors")
	askphotoconsent = models.BooleanField(null=False, blank=False, default=True, verbose_name="Field: photo consent", help_text="Include field for getting photo consent")
	skill_levels = models.BooleanField(blank=False, null=False, default=True)
	additionalintro = models.TextField(blank=True, null=False, help_text="Additional text shown just before the list of available additional options")
	jinjadir = models.CharField(max_length=200, blank=True, null=True, default=None, help_text="Full path to new style jinja repository root")
	callforpapersintro = models.TextField(blank=True, null=False)

	sendwelcomemail = models.BooleanField(blank=False, null=False, default=False, verbose_name="Send welcome email", help_text="Send an email to attendees once their registration is completed.")
	welcomemail = models.TextField(blank=True, null=False, verbose_name="Welcome email contents")

	lastmodified = models.DateTimeField(auto_now=True, null=False, blank=False)
	newsjson = models.CharField(max_length=128, blank=True, null=True, default=None)
	accounting_object = models.CharField(max_length=30, blank=True, null=True, verbose_name="Accounting object name")
	vat_registrations = models.ForeignKey(VatRate, null=True, blank=True, verbose_name='VAT rate for registrations', related_name='vat_registrations')
	vat_sponsorship = models.ForeignKey(VatRate, null=True, blank=True, verbose_name='VAT rate for sponsorships', related_name='vat_sponsorship')
	invoice_autocancel_hours = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1),], verbose_name="Autocancel invoices", help_text="Automatically cancel invoices after this many hours")
	attendees_before_waitlist = models.IntegerField(blank=False, null=False, default=0, validators=[MinValueValidator(0),], verbose_name="Attendees before waitlist", help_text="Maximum number of attendees before enabling waitlist management. 0 for no waitlist management")
	series = models.ForeignKey(ConferenceSeries, null=False, blank=False)
	personal_data_purged = models.DateTimeField(null=True, blank=True, help_text="Personal data for registrations for this conference have been purged")

	# Attributes that are safe to access in jinja templates
	_safe_attributes = ('active', 'askfood', 'askshareemail', 'asktshirt', 'asktwitter', 'asknick',
						'callforpapersintro', 'callforpapersopen',
						'conferencefeedbackopen', 'confurl', 'contactaddr',
						'feedbackopen', 'org_name', 'skill_levels', 'treasurer_email', 'urlname', )

	def __unicode__(self):
		return self.conferencename

	class Meta:
		ordering = [ '-startdate', ]

	@property
	def conferencedatestr(self):
		if self.enddate and not self.startdate==self.enddate:
			return "%s - %s" % (
				self.startdate.strftime("%Y-%m-%d"),
				self.enddate.strftime("%Y-%m-%d")
			)
		else:
			return self.startdate.strftime("%Y-%m-%d")

	@property
	def pending_session_notifications(self):
		# How many speaker notifications are currently pending for this
		# conference. Note that this will always be zero if the conference
		# is in the past (so we don't end up with unnecessary db queries)
		if self.enddate:
			if self.enddate < datetime.datetime.today().date():
				return 0
		else:
			if self.startdate < datetime.datetime.today().date():
				return 0
		return self.conferencesession_set.exclude(status=F('lastnotifiedstatus')).count()

	def waitlist_active(self):
		if self.attendees_before_waitlist == 0:
			# Never on waitlist if waitlisting is not turned on
			return False

		# Any registrations that are completed, has an invoice, or has a
		# bulk payment will count against the total.
		num = ConferenceRegistration.objects.filter(Q(conference=self) & (Q(payconfirmedat__isnull=False) | Q(invoice__isnull=False) | Q(bulkpayment__isnull=False))).count()
		if num >= self.attendees_before_waitlist:
			return True

		return False

	@property
	def needs_data_purge(self):
		return self.enddate < datetime.date.today() and not self.personal_data_purged

	def clean(self):
		cc = super(Conference, self).clean()
		if self.sendwelcomemail and not self.welcomemail:
			raise ValidationError("Must specify an actual welcome mail if it's enabled!")

class RegistrationClass(models.Model):
	conference = models.ForeignKey(Conference, null=False)
	regclass = models.CharField(max_length=64, null=False, blank=False, verbose_name="Registration class")
	badgecolor = models.CharField(max_length=20, null=False, blank=True, verbose_name="Badge color", help_text='Badge background color in hex format', validators=[color_validator, ])
	badgeforegroundcolor = models.CharField(max_length=20, null=False, blank=True, verbose_name="Badge foreground", help_text='Badge foreground color in hex format', validators=[color_validator, ])

	def __unicode__(self):
		return self.regclass

	def colortuple(self):
		return tuple([int(self.badgecolor[n*2+1:n*2+2+1], 16) for n in range(0,3)])

	@property
	def bgcolortuplestr(self):
		if len(self.badgecolor):
			return ','.join(map(str, self.colortuple()))
		else:
			return None

	def foregroundcolortuple(self):
		if len(self.badgeforegroundcolor):
			return tuple([int(self.badgeforegroundcolor[n*2+1:n*2+2+1], 16) for n in range(0,3)])
		else:
			return None

	@property
	def fgcolortuplestr(self):
		if self.badgeforegroundcolor:
			return ','.join(map(str, self.foregroundcolortuple()))
		else:
			return None

	class Meta:
		verbose_name_plural = 'Registration classes'

	def safe_export(self):
		attribs = ['regclass', 'badgecolor', 'badgeforegroundcolor', 'bgcolortuplestr', 'fgcolortuplestr']
		d = dict((a, getattr(self, a) and unicode(getattr(self, a))) for a in attribs)
		return d

class RegistrationDay(models.Model):
	conference = models.ForeignKey(Conference, null=False)
	day = models.DateField(null=False, blank=False)

	class Meta:
		ordering = ('day', )
		unique_together = (
			('conference', 'day'),
		)

	def __unicode__(self):
		return self.day.strftime('%a, %d %b')

	def shortday(self):
		df = DateFormat(self.day)
		return df.format('D jS')

class RegistrationType(models.Model):
	conference = models.ForeignKey(Conference, null=False)
	regtype = models.CharField(max_length=64, null=False, blank=False)
	regclass = models.ForeignKey(RegistrationClass, null=True, blank=True)
	cost = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, help_text="Cost excluding VAT.")
	active = models.BooleanField(null=False, blank=False, default=True)
	activeuntil = models.DateField(null=True, blank=True)
	inlist = models.BooleanField(null=False, blank=False, default=True)
	sortkey = models.IntegerField(null=False, blank=False, default=10)
	specialtype = models.CharField(max_length=5, blank=True, null=True, choices=special_reg_types)
	require_phone = models.BooleanField(null=False, blank=False, default=False, help_text="Require phone number to be entered")
	days = models.ManyToManyField(RegistrationDay, blank=True)
	alertmessage =models.TextField(null=False, blank=True)
	upsell_target = models.BooleanField(null=False, blank=False, default=False, help_text='Is target registration type for upselling in order to add additional options')
	invoice_autocancel_hours = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1),], verbose_name="Autocancel invoices", help_text="Automatically cancel invoices after this many hours")
	requires_option = models.ManyToManyField('ConferenceAdditionalOption', blank=True, help_text='Requires at least one of the selected additional options to be picked')

	class Meta:
		ordering = ['conference', 'sortkey', ]

	def __unicode__(self):
		if self.cost == 0:
			return self.regtype
		else:
			return "%s (%s %s)" % (self.regtype,
								   settings.CURRENCY_ABBREV,
								   self.total_cost)

	@property
	def total_cost(self):
		if self.conference.vat_registrations:
			return "%.2f incl VAT" % (self.cost * (1+self.conference.vat_registrations.vatpercent/Decimal(100.0)))
		else:
			return self.cost

	@property
	def available_days(self):
		dd = list(self.days.all())
		if len(dd) == 1:
			return dd[0].shortday()
		return ", ".join([x.shortday() for x in dd[:-1]]) + " and " + dd[-1].shortday()

	def safe_export(self):
		attribs = ['regtype', 'specialtype']
		d = dict((a, getattr(self, a) and unicode(getattr(self, a))) for a in attribs)
		d['regclass'] = self.regclass and self.regclass.safe_export()
		d['days'] = [dd.day.strftime('%Y-%m-%d') for dd in self.days.all()]
		return d

class ShirtSize(models.Model):
	shirtsize = models.CharField(max_length=32)
	sortkey = models.IntegerField(default=100, null=False, blank=False)

	def __unicode__(self):
		return self.shirtsize

	class Meta:
		ordering = ('sortkey', 'shirtsize',)

class ConferenceAdditionalOption(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	name = models.CharField(max_length=100, null=False, blank=False)
	cost = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, help_text="Cost excluding VAT.")
	maxcount = models.IntegerField(null=False)
	public = models.BooleanField(null=False, blank=False, default=True, help_text='Visible on public forms (opposite of admin only)')
	upsellable = models.BooleanField(null=False, blank=False, default=True, help_text='Can this option be purchased after the registration is completed')
	invoice_autocancel_hours = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1),], verbose_name="Autocancel invoices", help_text="Automatically cancel invoices after this many hours")
	requires_regtype = models.ManyToManyField(RegistrationType, blank=True, help_text='Can only be picked with selected registration types')
	mutually_exclusive = models.ManyToManyField('self', blank=True, help_text='Mutually exlusive with these additional options', symmetrical=True)

	class Meta:
		ordering = ['name', ]

	def __unicode__(self):
		# This is what renders in the multichoice checkboxes, so make
		# it nice for the end user.
		if self.cost > 0:
			if self.conference.vat_registrations:
				coststr = " (%s %.2f)" % (settings.CURRENCY_ABBREV, self.cost * (1+self.conference.vat_registrations.vatpercent/Decimal(100.0)))
			else:
				coststr = " (%s %s)" % (settings.CURRENCY_ABBREV, self.cost)
		else:
			coststr = ""
		if self.maxcount == -1:
			return "%s%s (currently not available)" % (self.name, coststr)
		if self.maxcount > 0:
			usedcount = self.conferenceregistration_set.count()
			return "%s%s (%s of %s available)" % (self.name, coststr,
												  self.maxcount - usedcount,
												  self.maxcount)
		return "%s%s" % (self.name, coststr)

class BulkPayment(models.Model):
	# User that owns this bulk payment
	user = models.ForeignKey(User, null=False, blank=False)

	# We attach it to a specific conference
	conference = models.ForeignKey(Conference, null=False, blank=False)

	# Invoice, once one has been created
	invoice = models.ForeignKey(Invoice, null=True, blank=True)
	numregs = models.IntegerField(null=False, blank=False)

	createdat = models.DateField(null=False, blank=False, auto_now_add=True)
	paidat = models.DateField(null=True, blank=True)

	def ispaid(self):
		return self.paidat and True or False
	ispaid.boolean = True

	def adminstring(self):
		return "%s at %s" % (self.user, self.createdat)

	@property
	def payment_method_description(self):
		if not self.paidat:
			return "not paid."
		if self.invoice:
			if self.invoice.paidat:
				return "paid with invoice #{0}.\nInvoice {1}".format(self.invoice.id, self.invoice.payment_method_description)
			else:
				return "supposedly paid with invoice #{0}, which is not flagged as paid. SOMETHING IS WRONG!".format(self.invoice.id)
		else:
			return "no invoice assigned. SOMETHING IS WRONG!"

	def __unicode__(self):
		return u"Bulk payment for %s created %s (%s registrations, %s%s): %s" % (
			self.conference,
			self.createdat,
			self.numregs,
			settings.CURRENCY_SYMBOL.decode('utf8'),
			self.invoice.total_amount,
			self.paidat and 'Paid' or 'Not paid yet')

class ConferenceRegistration(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	regtype = models.ForeignKey(RegistrationType, null=True, blank=True, verbose_name="Registration type")
	attendee = models.ForeignKey(User, null=True, blank=True)
	registrator = models.ForeignKey(User, null=False, blank=False, related_name="registrator")
	firstname = models.CharField(max_length=100, null=False, blank=False, verbose_name="First name")
	lastname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Last name")
	email = models.EmailField(null=False, blank=False, verbose_name="E-mail address")
	company = models.CharField(max_length=100, null=False, blank=True, verbose_name="Company")
	address = models.TextField(max_length=200, null=False, blank=True, verbose_name="Address")
	country = models.ForeignKey(Country, null=False, blank=False, verbose_name="Country")
	phone = models.CharField(max_length=100, null=False, blank=True, verbose_name="Phone number")
	shirtsize = models.ForeignKey(ShirtSize, null=True, blank=True, verbose_name="Preferred T-shirt size")
	dietary = models.CharField(max_length=100, null=False, blank=True, verbose_name="Special dietary needs")
	additionaloptions = models.ManyToManyField(ConferenceAdditionalOption, blank=True, verbose_name="Additional options")
	twittername = models.CharField(max_length=100, null=False, blank=True, verbose_name="Twitter account")
	nick = models.CharField(max_length=100, null=False, blank=True, verbose_name="Nickname")
	shareemail = models.BooleanField(null=False, blank=False, default=False, verbose_name="Share e-mail address with sponsors")
	photoconsent = models.NullBooleanField(null=True, blank=False, verbose_name="Consent to having your photo taken at the event by the organisers")

	# Admin fields!
	payconfirmedat = models.DateTimeField(null=True, blank=True, verbose_name="Payment confirmed")
	payconfirmedby = models.CharField(max_length=16, null=True, blank=True, verbose_name="Payment confirmed by")
	created = models.DateTimeField(null=False, blank=False, verbose_name="Registration created")
	lastmodified = models.DateTimeField(null=False, blank=False, auto_now=True)

	# If an invoice is generated, link to it here so we can find our
	# way back easily.
	invoice = models.ForeignKey(Invoice, null=True, blank=True)
	bulkpayment = models.ForeignKey(BulkPayment, null=True, blank=True)

	# Any voucher codes. This is just used as temporary storage, and as
	# such we don't try to make it a foreign key. Must be re-validated
	# everytime it's used.
	# It's also used for discount codes - another reason to not use a
	# foreign key :)
	vouchercode = models.CharField(max_length=100, null=False, blank=True, verbose_name='Voucher code')

	# Token to uniquely identify this registration in case we want to
	# access it without a login.
	regtoken = models.TextField(null=False, blank=False, unique=True)

	@property
	def fullname(self):
		return "%s %s" % (self.firstname, self.lastname)

	def has_invoice(self):
		# Return if this registration has an invoice, whether through
		# a direct invoice or a bulk payment.
		if not self.invoice is None:
			return True
		if not self.bulkpayment is None:
			return True
		return False
	has_invoice.boolean = True

	@property
	def invoice_status(self):
		if self.payconfirmedat:
			return "paid and confirmed"
		elif self.invoice:
			return "invoice generated, not paid"
		elif self.bulkpayment:
			return "bulk invoice generated, not paid"
		else:
			return "pending"

	@property
	def can_edit(self):
		return not (self.payconfirmedat or self.invoice or self.bulkpayment)

	def short_regtype(self):
		if self.regtype:
			return self.regtype.regtype[:30]
		return None
	short_regtype.short_description = 'Reg type'

	@property
	def additionaloptionlist(self):
		return ",\n".join([a.name for a in self.additionaloptions.all()])

	@property
	def is_volunteer(self):
		return self.volunteers_set.exists()

	@property
	def payment_method_description(self):
		if not self.payconfirmedat:
			return "Not paid."
		if self.payconfirmedby == "no payment reqd":
			return "Registration does not require payment."
		if self.payconfirmedby == "Multireg/nopay":
			return "Registration is part of multi payment batch that does not require payment."
		if self.payconfirmedby == "Invoice paid":
			# XXX dig deeper!
			return "Paid by individual invoice #{0}.\n Invoice {1}".format(self.invoice.id, self.invoice.payment_method_description)
		if self.payconfirmedby == "Bulk paid":
			return "Paid by bulk payment #{0}.\n Bulk {1}".format(self.bulkpayment.id, self.bulkpayment.payment_method_description)

		return "Payment details not available"

	# For the admin interface (mainly)
	def __unicode__(self):
		return "%s: %s %s <%s>" % (self.conference, self.firstname, self.lastname, self.email)

	# For exporting "safe attributes" to external systems
	def safe_export(self):
		attribs = ['firstname', 'lastname', 'email', 'company', 'address', 'country', 'phone', 'shirtsize', 'dietary', 'twittername', 'nick', 'shareemail',]
		d = dict((a, getattr(self, a) and unicode(getattr(self, a))) for a in attribs)
		if self.regtype:
			d['regtype'] = self.regtype.safe_export()
		else:
			d['regtype'] = None
		d['additionaloptions'] = [{'id': ao.id, 'name': ao.name} for ao in self.additionaloptions.all()]
		return d

class RegistrationWaitlistEntry(models.Model):
	registration = models.OneToOneField(ConferenceRegistration, primary_key=True)
	enteredon = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	offeredon = models.DateTimeField(null=True, blank=True)
	offerexpires = models.DateTimeField(null=True, blank=True)

	@property
	def offers_made(self):
		return self.registrationwaitlisthistory_set.filter(text__startswith='Made offer').count()

class RegistrationWaitlistHistory(models.Model):
	waitlist = models.ForeignKey(RegistrationWaitlistEntry, null=False, blank=False)
	time = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	text = models.CharField(max_length=200, null=False, blank=False)

	class Meta:
		ordering = ('-time',)

class Track(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	trackname = models.CharField(max_length=100, null=False, blank=False)
	color = models.CharField(max_length=20, null=False, blank=True, validators=[color_validator, ])
	sortkey = models.IntegerField(null=False, default=100, blank=False)
	incfp = models.BooleanField(null=False, default=False, blank=False)

	json_included_attributes = ['trackname', 'color', 'sortkey', 'incfp']

	def __unicode__(self):
		return self.trackname

class Room(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	roomname = models.CharField(max_length=20, null=False, blank=False)
	sortkey = models.IntegerField(null=False, blank=False, default=100)

	json_included_attributes = ['roomname', 'sortkey']

	def __unicode__(self):
		return self.roomname

	class Meta:
		ordering = [ 'sortkey', 'roomname', ]


def _get_upload_path(instance, filename):
	return "%s" % instance.id

class Speaker(models.Model):
	user = models.OneToOneField(User, null=True, blank=True, unique=True)
	fullname = models.CharField(max_length=100, null=False, blank=False)
	twittername = models.CharField(max_length=32, null=False, blank=True)
	company = models.CharField(max_length=100, null=False, blank=True)
	abstract = models.TextField(null=False, blank=True)
	photofile = models.ImageField(upload_to=_get_upload_path, storage=SpeakerImageStorage(), blank=True, null=True, verbose_name="Photo")
	lastmodified = models.DateTimeField(auto_now=True, null=False, blank=False)
	speakertoken = models.TextField(null=False, blank=False, unique=True)

	_safe_attributes = ('id', 'name', 'fullname', 'twittername', 'company', 'abstract' ,'photofile', 'lastmodified', 'org_name', 'treasurer_email')
	json_included_attributes = ['fullname', 'twittername', 'company', 'abstract', 'lastmodified']

	@property
	def name(self):
		return self.fullname

	@property
	def email(self):
		if self.user:
			return self.user.email
		else:
			return None

	def has_abstract(self):
		return len(self.abstract)>0
	has_abstract.boolean = True

	def has_photo(self):
		return (self.photofile != None and self.photofile != "")
	has_photo.boolean= True

	def __unicode__(self):
		return self.name

	class Meta:
		ordering = ['fullname', ]

class DeletedItems(models.Model):
	itemid = models.IntegerField(null=False, blank=False)
	type = models.CharField(max_length=16, blank=False, null=False)
	deltime = models.DateTimeField(blank=False, null=False)

class Speaker_Photo(models.Model):
	speaker = models.OneToOneField(Speaker, db_column='id', primary_key=True)
	photo = models.TextField(null=False, blank=False)

	def __unicode__(self):
		return self.speaker.name

	def delete(self):
		# Remove reference from speaker, so we don't think the pic is there
		self.speaker.photofile = None
		self.speaker.save()
		super(Speaker_Photo, self).delete()

class ConferenceSessionScheduleSlot(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	starttime = models.DateTimeField(null=False, blank=False)
	endtime = models.DateTimeField(null=False, blank=False)

	def __unicode__(self):
		return "%s - %s" % (self.starttime, self.endtime)

class ConferenceSession(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	speaker = models.ManyToManyField(Speaker, blank=True)
	title = models.CharField(max_length=200, null=False, blank=False)
	starttime = models.DateTimeField(null=True, blank=True)
	endtime = models.DateTimeField(null=True, blank=True)
	track = models.ForeignKey(Track, null=True, blank=True)
	room = models.ForeignKey(Room, null=True, blank=True)
	cross_schedule = models.BooleanField(null=False, default=False)
	can_feedback = models.BooleanField(null=False, default=True)
	abstract = models.TextField(null=False, blank=True)
	skill_level = models.IntegerField(null=False, default=1, choices=SKILL_CHOICES)
	status = models.IntegerField(null=False, default=0, choices=STATUS_CHOICES)
	lastnotifiedstatus = models.IntegerField(null=False, default=0, choices=STATUS_CHOICES)
	lastnotifiedtime = models.DateTimeField(null=True, blank=True, verbose_name="Notification last sent")
	submissionnote = models.TextField(null=False, blank=True, verbose_name="Submission notes")
	initialsubmit = models.DateTimeField(null=True, blank=True, verbose_name="Submitted")
	tentativescheduleslot = models.ForeignKey(ConferenceSessionScheduleSlot, null=True, blank=True)
	tentativeroom = models.ForeignKey(Room, null=True, blank=True, related_name='tentativeroom')
	lastmodified = models.DateTimeField(auto_now=True, null=False, blank=False)

	# NOTE! Any added fields need to be considered for inclusion in
	# forms.CallForPapersForm and in views.callforpapers_copy()!

	# Not a db field, but set from the view to track if the current user
	# has given any feedback on this session.
	has_given_feedback = False

	@property
	def speaker_list(self):
		return ", ".join([s.name for s in self.speaker.all()])

	@property
	def skill_level_string(self):
		return (t for v,t in SKILL_CHOICES if v==self.skill_level).next()

	@property
	def status_string(self):
		return get_status_string(self.status)

	@property
	def status_string_long(self):
		return get_status_string_long(self.status)

	@property
	def lastnotified_status_string(self):
		return get_status_string(self.lastnotifiedstatus)

	@property
	def has_feedback(self):
		return self.conferencesessionfeedback_set.exists()

	def __unicode__(self):
		return "%s: %s (%s)" % (
			self.speaker_list,
			self.title,
			self.starttime,
		)

	@property
	def shorttitle(self):
		return "%s (%s)" % (
			self.title,
			self.starttime,
		)

	@property
	def utcstarttime(self):
		return self._utc_time(self.starttime + datetime.timedelta(hours=self.conference.timediff))

	@property
	def utcendtime(self):
		return self._utc_time(self.endtime + datetime.timedelta(hours=self.conference.timediff))

	def _utc_time(self, time):
		if not hasattr(self, '_localtz'):
			self._localtz = pytz.timezone(settings.TIME_ZONE)
		return self._localtz.localize(time).astimezone(pytz.utc)

	class Meta:
		ordering = [ 'starttime', ]

class ConferenceSessionSlides(models.Model):
	session = models.ForeignKey(ConferenceSession, null=False, blank=False)
	name = models.CharField(max_length=100, null=False, blank=False)
	url = models.URLField(max_length=1000, null=False, blank=True)
	content = models.BinaryField(null=True, blank=False)

	_safe_attributes = ('id', 'name', 'url', 'content')

class ConferenceSessionVote(models.Model):
	session = models.ForeignKey(ConferenceSession, null=False, blank=False)
	voter = models.ForeignKey(User, null=False, blank=False)
	vote = models.IntegerField(null=True, blank=False)
	comment = models.CharField(max_length=200, null=True, blank=True)

	class Meta:
		unique_together = ( ('session', 'voter',), )

class ConferenceSessionFeedback(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	session = models.ForeignKey(ConferenceSession, null=False, blank=False)
	attendee = models.ForeignKey(User, null=False, blank=False)
	topic_importance = models.IntegerField(null=False, blank=False)
	content_quality = models.IntegerField(null=False, blank=False)
	speaker_knowledge = models.IntegerField(null=False, blank=False)
	speaker_quality = models.IntegerField(null=False, blank=False)
	speaker_feedback = models.TextField(null=False, blank=True, verbose_name='Comments to the speaker')
	conference_feedback = models.TextField(null=False, blank=True, verbose_name='Comments to the conference organizers')

	def __unicode__(self):
		return unicode("%s - %s (%s)") % (self.conference, self.session, self.attendee)

class ConferenceFeedbackQuestion(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	question = models.CharField(max_length=100, null=False, blank=False)
	isfreetext = models.BooleanField(blank=False, null=False, default=False)
	textchoices = models.CharField(max_length=500, null=False, blank=True)
	sortkey = models.IntegerField(null=False, default=100)
	newfieldset = models.CharField(max_length=100, null=False, blank=True)

	def __unicode__(self):
		return "%s: %s" % (self.conference, self.question)

	class Meta:
		ordering = ['conference', 'sortkey', ]

class ConferenceFeedbackAnswer(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	question = models.ForeignKey(ConferenceFeedbackQuestion, null=False, blank=False)
	attendee = models.ForeignKey(User, null=False, blank=False)
	rateanswer = models.IntegerField(null=True)
	textanswer = models.TextField(null=False, blank=True)

	def __unicode__(self):
		return "%s - %s: %s" % (self.conference, self.attendee, self.question.question)

	class Meta:
		ordering = ['conference', 'attendee', 'question', ]

class VolunteerSlot(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	timerange = DateTimeRangeField(null=False, blank=False)
	title = models.CharField(max_length=50, null=False, blank=False)
	min_staff = models.IntegerField(null=False, blank=False, default=1, validators=[MinValueValidator(1)])
	max_staff = models.IntegerField(null=False, blank=False, default=1, validators=[MinValueValidator(1)])

	class Meta:
		ordering = [ 'timerange', ]

	def __unicode__(self):
		return self._display_timerange()

	def _display_timerange(self):
		return "{0} - {1}".format(self.timerange.lower, self.timerange.upper)

	@property
	def countvols(self):
		return self.volunteerassignment_set.all().count()

	@property
	def weekday(self):
		return self.timerange.lower.strftime('%Y-%m-%d (%A)')

	@property
	def utcstarttime(self):
		return self._utc_time(self.timerange.lower + datetime.timedelta(hours=self.conference.timediff))

	@property
	def utcendtime(self):
		return self._utc_time(self.timerange.upper + datetime.timedelta(hours=self.conference.timediff))

	def _utc_time(self, time):
		if not hasattr(self, '_localtz'):
			self._localtz = pytz.timezone(settings.TIME_ZONE)
		return self._localtz.localize(time).astimezone(pytz.utc)

class VolunteerAssignment(models.Model):
	slot = models.ForeignKey(VolunteerSlot, null=False, blank=False)
	reg = models.ForeignKey(ConferenceRegistration, null=False, blank=False)
	vol_confirmed = models.BooleanField(null=False, blank=False, default=False, verbose_name="Confirmed by volunteer")
	org_confirmed = models.BooleanField(null=False, blank=False, default=False, verbose_name="Confirmed by organizers")

	_safe_attributes = ('id', 'slot', 'reg', 'vol_confirmed', 'org_confirmed')

class PrepaidBatch(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	regtype = models.ForeignKey(RegistrationType, null=False, blank=False)
	buyer = models.ForeignKey(User, null=False, blank=False)
	buyername = models.CharField(max_length=100, null=True, blank=True)
	sponsor = models.ForeignKey('confsponsor.Sponsor', null=True, blank=True, verbose_name="Optional sponsor")

	def __unicode__(self):
		return "%s: %s for %s" % (self.conference, self.regtype, self.buyer)

	class Meta:
		verbose_name_plural = "Prepaid batches"
		ordering = ['conference', 'id', ]

class PrepaidVoucher(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	vouchervalue = models.CharField(max_length=100, null=False, blank=False, unique=True)
	batch = models.ForeignKey(PrepaidBatch, null=False, blank=False)
	user = models.ForeignKey(ConferenceRegistration, null=True, blank=True)
	usedate = models.DateTimeField(null=True, blank=True)

	def __unicode__(self):
		return self.vouchervalue

	class Meta:
		ordering = ['batch', 'vouchervalue', ]

class DiscountCode(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	code = models.CharField(max_length=100, null=False, blank=False)
	discountamount = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0)
	discountpercentage = models.IntegerField(null=False, blank=False, default=0)
	regonly = models.BooleanField(null=False, blank=False, default=False, help_text="Apply percentage discount only to the registration cost, not additional options. By default, it's applied to both.")
	validuntil = models.DateField(blank=True, null=True)
	maxuses = models.IntegerField(null=False, blank=False, default=0)
	requiresoption = models.ManyToManyField(ConferenceAdditionalOption, blank=True, help_text='Requires this option to be set in order to be valid')
	requiresregtype = models.ManyToManyField(RegistrationType, blank=True, help_text='Require a specific registration type to be valid')

	registrations = models.ManyToManyField(ConferenceRegistration, blank=True)

	# If this discount code is purchased by a sponsor, track it here.
	sponsor = models.ForeignKey('confsponsor.Sponsor', null=True, blank=True, verbose_name="Optional sponsor.", help_text="Note that if a sponsor is picked, an invoice will be generated once the discount code closes!!!")
	sponsor_rep = models.ForeignKey(User, null=True, blank=True, verbose_name="Optional sponsor representative.", help_text="Must be set if the sponsor field is set!")
	is_invoiced = models.BooleanField(null=False, blank=False, default=False, verbose_name="Has an invoice been sent for this discount code.")

	def __unicode__(self):
		return self.code

	class Meta:
		unique_together = ( ('conference', 'code',), )
		ordering = ('conference', 'code',)

	@property
	def count(self):
		return self.registrations.count()

class AttendeeMail(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	regclasses = models.ManyToManyField(RegistrationClass, blank=False)
	sentat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	subject = models.CharField(max_length=100, null=False, blank=False)
	message = models.TextField(max_length=8000, null=False, blank=False)

	def __unicode__(self):
		return "%s: %s" % (self.sentat.strftime("%Y-%m-%d %H:%M"), self.subject)

	class Meta:
		ordering = ('-sentat', )


class PendingAdditionalOrder(models.Model):
	reg = models.ForeignKey(ConferenceRegistration, null=False, blank=False)
	options = models.ManyToManyField(ConferenceAdditionalOption, blank=False)
	newregtype = models.ForeignKey(RegistrationType, null=True, blank=True)
	createtime = models.DateTimeField(null=False, blank=False)
	invoice = models.ForeignKey(Invoice, null=True, blank=True)
	payconfirmedat = models.DateTimeField(null=True, blank=True)

	def __unicode__(self):
		return u"%s" % (self.reg, )



class AggregatedTshirtSizes(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	size = models.ForeignKey(ShirtSize, null=False, blank=False)
	num = models.IntegerField(null=False, blank=False)

	class Meta:
		unique_together = ( ('conference', 'size'), )

class AggregatedDietary(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	dietary = models.CharField(max_length=100, null=False, blank=False)
	num = models.IntegerField(null=False, blank=False)

	class Meta:
		unique_together = ( ('conference', 'dietary'), )


AccessTokenPermissions = (
	('regtypes', 'Registration types and counters'),
	('discounts', 'Discount codes'),
	('vouchers', 'Voucher codes'),
	('sponsors', 'Sponsors and counts'),
)

class AccessToken(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	token = models.CharField(max_length=200, null=False, blank=False)
	description = models.TextField(null=False, blank=False)
	permissions = ChoiceArrayField(
		models.CharField(max_length=32, blank=False, null=False, choices=AccessTokenPermissions)
	)

	class Meta:
		unique_together = ( ('conference', 'token'), )

	def __unicode__(self):
		return self.token

	def _display_permissions(self):
		return ", ".join(self.permissions)
