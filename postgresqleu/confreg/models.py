#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.db import models
from django.db.models import Q
from django.db.models.expressions import F
from django.db.models.signals import pre_save
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils.dateformat import DateFormat
from django.utils.functional import cached_property
from django.utils import timezone
from django.template.defaultfilters import slugify
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.indexes import GinIndex
from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver

from postgresqleu.util.validators import validate_lowercase, validate_urlname
from postgresqleu.util.validators import TwitterValidator
from postgresqleu.util.validators import PictureUrlValidator
from postgresqleu.util.forms import ChoiceArrayField
from postgresqleu.util.fields import LowercaseEmailField, ImageBinaryField, PdfBinaryField
from postgresqleu.util.time import today_conference
from postgresqleu.util.db import exec_no_result
from postgresqleu.util.image import rescale_image_bytes

import base64
import pytz
from decimal import Decimal

from postgresqleu.countries.models import Country
from postgresqleu.invoices.models import Invoice, VatRate, InvoicePaymentMethod
from postgresqleu.newsevents.models import NewsPosterProfile

from .regtypes import special_reg_types

SKILL_CHOICES = (
    (0, "Beginner"),
    (1, "Intermediate"),
    (2, "Advanced"),
)

TWITTER_POST_CHOICES = (
    (0, "Nobody can post"),
    (1, "Admins can post without approval, volunteers can't post"),
    (2, "Volunteers can post, require admin approval"),
    (3, "Volunteers can post, require volunteer or admin approval"),
    (4, "Volunteers and admins can post without approval"),
)

# NOTE! The contents of these arrays must also be matched with the
# database table confreg_status_strings. This one is managed by
# manually creating a separate migration in case the contents change.
STATUS_CHOICES = (
    (0, "Submitted"),
    (1, "Approved"),
    (2, "Not Accepted"),
    (3, "Pending"),      # Approved, but not confirmed
    (4, "Reserve"),      # Reserve list
    (5, 'Pending reserve'),  # Reserve list, but not confirmed
    (6, 'Withdrawn'),    # Withdrawn by speaker
)
STATUS_CHOICES_LONG = (
    (0, "Submitted, not processed yet"),
    (1, "Approved and confirmed"),
    (2, "Not Accepted"),
    (3, "Pending speaker confirmation"),               # Approved, but not confirmed
    (4, "Reserve-listed in case of cancels/changes"),  # Reserve list
    (5, "Pending reserve-list confirmation"),          # Reserve list, but not confirmed
    (6, "Withdrawn by speaker"),
)
STATUS_CHOICES_SHORT = (
    (0, "submitted"),
    (1, "approved"),
    (2, "notaccepted"),
    (3, "pending"),               # Approved, but not confirmed
    (4, "reserve"),  # Reserve list
    (5, "pendreserve"),
    (6, "withdrawn"),
)

PRIMARY_SPEAKER_PHOTO_RESOLUTION = (512, 512)


def get_status_string(val):
    return next((t for v, t in STATUS_CHOICES if v == val))


def get_status_string_long(val):
    return next((t for v, t in STATUS_CHOICES_LONG if v == val))


def get_status_string_short(val):
    return next((t for v, t in STATUS_CHOICES_SHORT if v == val))


valid_status_transitions = {
    0: {3: 'Talk approved', 2: 'Talk not accepted', 5: 'Talk added to reserve list'},
    1: {6: 'Talk withdrawn', },
    2: {0: 'Talk processing reset', },
    3: {0: 'Talk unapproved', 1: 'Speaker confirms', 6: 'Speaker declines'},
    4: {1: 'Last-minute reservelist', 3: 'Activated from reservelist', 6: 'Talk withdrawn'},
    5: {4: 'Talk confirmed to reservelist', 6: 'Speaker withdraws'},
    6: {0: 'Talk processing reset', },
}


def color_validator(value):
    if not value.startswith('#'):
        raise ValidationError('Color values must start with #')
    if len(value) != 7:
        raise ValidationError('Color values must be # + 7 characters')
    for n in range(0, 3):
        try:
            int(value[n * 2 + 1:n * 2 + 2 + 1], 16)
        except ValueError:
            raise ValidationError('Invalid value in color specification')


class ConferenceSeries(models.Model):
    name = models.CharField(max_length=64, blank=False, null=False)
    sortkey = models.IntegerField(null=False, default=100)
    intro = models.TextField(blank=True, null=False)
    visible = models.BooleanField(null=False, default=True)
    administrators = models.ManyToManyField(User, blank=True)

    _safe_attributes = ('name', 'intro', 'visible')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('sortkey', 'name')
        verbose_name_plural = "Conference series"


class ConferenceSeriesOptOut(models.Model):
    # Users opting out of communications about a specific conference
    series = models.ForeignKey(ConferenceSeries, null=False, blank=False, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)

    class Meta:
        unique_together = (
            ('user', 'series'),
        )


class GlobalOptOut(models.Model):
    # Users who are opting out of *all* future communications
    user = models.OneToOneField(User, null=False, blank=False, primary_key=True, on_delete=models.CASCADE)


class Conference(models.Model):
    urlname = models.CharField(max_length=32, blank=False, null=False, unique=True, validators=[validate_lowercase, validate_urlname, ], verbose_name="URL name")
    conferencename = models.CharField(max_length=64, blank=False, null=False, verbose_name="Conference name")
    startdate = models.DateField(blank=False, null=False, verbose_name="Start date", db_index=True)
    enddate = models.DateField(blank=False, null=False, verbose_name="End date")
    location = models.CharField(max_length=128, blank=False, null=False)
    promoactive = models.BooleanField(default=False, verbose_name="Promotion active")
    promopicurl = models.URLField(blank=True, null=False, verbose_name="URL to promo picture", validators=[PictureUrlValidator(aspect=2.3)])
    promotext = models.TextField(null=False, blank=True, max_length=1000, verbose_name="Promotion text")
    tzname = models.CharField(max_length=100, blank=False, null=False, verbose_name="Time zone", default=settings.TIME_ZONE)
    contactaddr = LowercaseEmailField(blank=False, null=False, verbose_name="Contact address")
    sponsoraddr = LowercaseEmailField(blank=False, null=False, verbose_name="Sponsor address")
    notifyaddr = LowercaseEmailField(blank=False, null=False, verbose_name="Notification address")
    notifyregs = models.BooleanField(blank=False, null=False, default=False, verbose_name="Notify about registrations")
    notifysessionstatus = models.BooleanField(blank=False, null=False, default=False, verbose_name="Notify about session status changes by speakers")
    notifyvolunteerstatus = models.BooleanField(blank=False, null=False, default=False, verbose_name="Notify about volunteer schedule changes")
    registrationopen = models.BooleanField(blank=False, null=False, default=False, verbose_name="Registration open")
    registrationtimerange = DateTimeRangeField(null=True, blank=True, verbose_name="Registration open between", help_text='Registration open between these times (if checkbox is also enabled).')
    callforpapersopen = models.BooleanField(blank=False, null=False, default=False, verbose_name="Call for papers open")
    callforpaperstimerange = DateTimeRangeField(null=True, blank=True, verbose_name="Call for papers open between", help_text='Call for papers open between these times (if checkbox is also enabled).')
    callforsponsorsopen = models.BooleanField(blank=False, null=False, default=False, verbose_name="Call for sponsors open")
    callforsponsorstimerange = DateTimeRangeField(null=True, blank=True, verbose_name="Call for sponsors open between", help_text='Call for sponsors open between these times (if checkbox is also enabled).')
    feedbackopen = models.BooleanField(blank=False, null=False, default=False, verbose_name="Session feedback open")
    conferencefeedbackopen = models.BooleanField(blank=False, null=False, default=False, verbose_name="Conference feedback open")
    allowedit = models.BooleanField(blank=False, null=False, default=True, verbose_name="Allow editing registrations")
    scheduleactive = models.BooleanField(blank=False, null=False, default=False, verbose_name="Schedule publishing active")
    sessionsactive = models.BooleanField(blank=False, null=False, default=False, verbose_name="Session list publishing active")
    cardsactive = models.BooleanField(blank=False, null=False, default=False, verbose_name="Card publishing active", help_text='Publish "cards" for sessions and speakers')
    checkinactive = models.BooleanField(blank=False, null=False, default=False, verbose_name="Check-in active")
    schedulewidth = models.IntegerField(blank=False, default=600, null=False, verbose_name="Width of HTML schedule")
    pixelsperminute = models.FloatField(blank=False, default=1.5, null=False, verbose_name="Vertical pixels per minute")
    confurl = models.CharField(max_length=128, blank=False, null=False, validators=[validate_lowercase, ], verbose_name="Conference URL")
    twitter_timewindow_start = models.TimeField(null=False, blank=False, default='00:00', verbose_name="Don't post tweets before")
    twitter_timewindow_end = models.TimeField(null=False, blank=False, default='23:59:59', verbose_name="Don't post tweets after")
    twitter_postpolicy = models.IntegerField(null=False, blank=False, default=0, choices=TWITTER_POST_CHOICES,
                                             verbose_name="Posting policy")
    slide_upload_reminder_days = models.IntegerField(
        blank=False,
        null=False,
        default=0,
        validators=[
            MinValueValidator(0),
        ],
        help_text="Days to wait before sending speakers reminder to upload their slides",
    )

    administrators = models.ManyToManyField(User, blank=True)
    testers = models.ManyToManyField(User, blank=True, related_name="testers_set", help_text="Users who can bypass the '<function> is open' check and access pages before they're open, in order to test")
    talkvoters = models.ManyToManyField(User, blank=True, related_name="talkvoters_set", help_text="Users who can view talks pre-approval, vote on the talks, and leave comments")
    staff = models.ManyToManyField(User, blank=True, related_name="staff_set", help_text="Users who can register as staff")
    volunteers = models.ManyToManyField('ConferenceRegistration', blank=True, related_name="volunteers_set", help_text="Users who volunteer")
    checkinprocessors = models.ManyToManyField('ConferenceRegistration', blank=True, related_name="checkinprocessors_set", verbose_name="Check-in processors", help_text="Users who process checkins")
    asktshirt = models.BooleanField(blank=False, null=False, default=True, verbose_name="Field: t-shirt", help_text="Include field for T-shirt size")
    askfood = models.BooleanField(blank=False, null=False, default=True, verbose_name="Field: dietary", help_text="Include field for dietary needs")
    asktwitter = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: twitter name", help_text="Include field for twitter name")
    asknick = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: nick", help_text="Include field for nick")
    askbadgescan = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: badge scanning", help_text="Include field for allowing sponsors to scan badge")
    askshareemail = models.BooleanField(null=False, blank=False, default=False, verbose_name="Field: share email", help_text="Include field for sharing email with sponsors")
    askphotoconsent = models.BooleanField(null=False, blank=False, default=True, verbose_name="Field: photo consent", help_text="Include field for getting photo consent")
    skill_levels = models.BooleanField(blank=False, null=False, default=True)
    additionalintro = models.TextField(blank=True, null=False, verbose_name="Additional options intro", help_text="Additional text shown just before the list of available additional options")
    jinjaenabled = models.BooleanField(null=False, blank=False, default=False, verbose_name="Jinja templates enabled")
    jinjadir = models.CharField(max_length=200, blank=True, null=True, default=None, help_text="Full path to new style jinja repository root", verbose_name="Jinja directory")
    callforpapersintro = models.TextField(blank=True, null=False, verbose_name="Call for papers intro")
    callforpaperstags = models.BooleanField(blank=False, null=False, default=False, verbose_name='Use tags')
    showvotes = models.BooleanField(blank=False, null=False, default=False, verbose_name="Show votes", help_text="Show other people's votes on the talkvote page")

    sendwelcomemail = models.BooleanField(blank=False, null=False, default=False, verbose_name="Send welcome email", help_text="Send an email to attendees once their registration is completed.")
    welcomemail = models.TextField(blank=True, null=False, verbose_name="Welcome email contents")
    tickets = models.BooleanField(blank=False, null=False, default=False, verbose_name="Use tickets", help_text="Generate and send tickets to all attendees once their registration is completed.")
    queuepartitioning = models.IntegerField(blank=True, null=True, choices=((1, 'By last name'), (2, 'By first name'), ), verbose_name="Queue partitioning", help_text="If queue partitioning is used, partition by what?")

    lastmodified = models.DateTimeField(auto_now=True, null=False, blank=False)
    accounting_object = models.CharField(max_length=30, blank=True, null=True, verbose_name="Accounting object name")
    vat_registrations = models.ForeignKey(VatRate, null=True, blank=True, verbose_name='VAT rate for registrations', related_name='vat_registrations', on_delete=models.CASCADE)
    vat_sponsorship = models.ForeignKey(VatRate, null=True, blank=True, verbose_name='VAT rate for sponsorships', related_name='vat_sponsorship', on_delete=models.CASCADE)
    invoice_autocancel_hours = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1), ], verbose_name="Autocancel invoices", help_text="Automatically cancel invoices after this many hours")
    paymentmethods = models.ManyToManyField(InvoicePaymentMethod, blank=True, verbose_name='Invoice payment options')
    attendees_before_waitlist = models.IntegerField(blank=False, null=False, default=0, validators=[MinValueValidator(0), ], verbose_name="Attendees before waitlist", help_text="Maximum number of attendees before enabling waitlist management. 0 for no waitlist management")
    series = models.ForeignKey(ConferenceSeries, null=False, blank=False, on_delete=models.CASCADE)
    personal_data_purged = models.DateTimeField(null=True, blank=True, help_text="Personal data for registrations for this conference have been purged")
    initial_common_countries = models.ManyToManyField(Country, blank=True, help_text="Initial set of common countries")
    key_public = models.TextField(null=False, blank=True, verbose_name="Public RSA key for signatures")
    key_private = models.TextField(null=False, blank=True, verbose_name="Private RSA key for signatures")
    web_origins = models.CharField(null=False, blank=True, max_length=1000, verbose_name="Allowed web origins for API calls (comma separated list)")

    # Attributes that are safe to access in jinja templates
    _safe_attributes = ('registrationopen', 'registrationtimerange', 'IsRegistrationOpen',
                        'askfood', 'askbadgescan', 'askshareemail', 'asktshirt', 'asktwitter', 'asknick',
                        'callforpapersintro', 'callforpapersopen', 'callforpaperstimerange', 'IsCallForPapersOpen',
                        'callforpaperstags', 'allowedit',
                        'conferencefeedbackopen', 'confurl', 'contactaddr', 'tickets',
                        'conferencedatestr', 'location', 'welcomemail',
                        'feedbackopen', 'skill_levels', 'urlname', 'conferencename',
                        'series',
    )

    def safe_export(self):
        d = dict((a, getattr(self, a) and str(getattr(self, a))) for a in self._safe_attributes)
        return d

    def __str__(self):
        return self.conferencename

    class Meta:
        ordering = ['-startdate', ]

    @cached_property
    def tzobj(self):
        return pytz.timezone(self.tzname)

    def localize_datetime(self, dt):
        return self.tzobj.localize(dt)

    @property
    def conferencedatestr(self):
        if self.enddate and not self.startdate == self.enddate:
            return "%s - %s" % (
                self.startdate.strftime("%Y-%m-%d"),
                self.enddate.strftime("%Y-%m-%d")
            )
        else:
            return self.startdate.strftime("%Y-%m-%d")

    @property
    def IsRegistrationOpen(self):
        # Check if the registration is open, including verifying against time range
        if not self.registrationopen:
            return False
        # It's open, but what does the time range say?
        if self.registrationtimerange is None:
            return True
        return timezone.now() in self.registrationtimerange

    @property
    def IsCallForPapersOpen(self):
        # Check if the call for papers is open, including verifying against time range
        if not self.callforpapersopen:
            return False
        # It's open, but what does the time range say?
        if self.callforpaperstimerange is None:
            return True
        return timezone.now() in self.callforpaperstimerange

    @property
    def IsCallForSponsorsOpen(self):
        if not self.callforsponsorsopen:
            return False
        if self.callforsponsorstimerange is None:
            return True
        return timezone.now() in self.callforsponsorstimerange

    @property
    def remove_fields(self):
        if not self.asktshirt:
            yield 'shirtsize'
        if not self.asknick:
            yield 'nick'
        if not self.asktwitter:
            yield 'twittername'
        if not self.askbadgescan:
            yield 'badgescan'
        if not self.askshareemail:
            yield 'shareemail'
        if not self.askphotoconsent:
            yield 'photoconsent'
        if not self.askfood:
            yield 'dietary'

    @property
    def pending_session_notifications(self):
        # How many speaker notifications are currently pending for this
        # conference. Note that this will always be zero if the conference
        # is in the past (so we don't end up with unnecessary db queries)
        if self.enddate:
            if self.enddate < today_conference():
                return 0
        else:
            if self.startdate < today_conference():
                return 0
        return self.conferencesession_set.exclude(status=F('lastnotifiedstatus')).exclude(speaker__isnull=True).count()

    def waitlist_active(self):
        if self.attendees_before_waitlist == 0:
            # Never on waitlist if waitlisting is not turned on
            return False

        # Any registrations that are completed, has an invoice, or has a
        # bulk payment will count against the total.
        num = ConferenceRegistration.objects.filter(Q(conference=self) & (Q(payconfirmedat__isnull=False, canceledat__isnull=True) | Q(invoice__isnull=False) | Q(bulkpayment__isnull=False))).count()
        if num >= self.attendees_before_waitlist:
            return True

        return False

    @cached_property
    def has_social_broadcast(self):
        return self.conferencemessaging_set.filter(broadcast=True, provider__active=True).exists()

    @property
    def needs_data_purge(self):
        return self.enddate < today_conference() and not self.personal_data_purged

    def clean(self):
        cc = super(Conference, self).clean()
        if self.sendwelcomemail and not self.welcomemail:
            raise ValidationError("Must specify an actual welcome mail if it's enabled!")
        return cc


class RegistrationClass(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    regclass = models.CharField(max_length=64, null=False, blank=False, verbose_name="Registration class")
    badgecolor = models.CharField(max_length=20, null=False, blank=True, verbose_name="Badge color", help_text='Badge background color in hex format', validators=[color_validator, ])
    badgeforegroundcolor = models.CharField(max_length=20, null=False, blank=True, verbose_name="Badge foreground", help_text='Badge foreground color in hex format', validators=[color_validator, ])

    def __str__(self):
        return self.regclass

    def colortuple(self):
        return tuple([int(self.badgecolor[n * 2 + 1:n * 2 + 2 + 1], 16) for n in range(0, 3)])

    @property
    def bgcolortuplestr(self):
        if len(self.badgecolor):
            return ','.join(map(str, self.colortuple()))
        else:
            return None

    def foregroundcolortuple(self):
        if len(self.badgeforegroundcolor):
            return tuple([int(self.badgeforegroundcolor[n * 2 + 1:n * 2 + 2 + 1], 16) for n in range(0, 3)])
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
        d = dict((a, getattr(self, a) and str(getattr(self, a))) for a in attribs)
        return d


class RegistrationDay(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    day = models.DateField(null=False, blank=False)

    class Meta:
        ordering = ('day', )
        unique_together = (
            ('conference', 'day'),
        )

    def __str__(self):
        return self.day.strftime('%a, %d %b')

    def shortday(self):
        df = DateFormat(self.day)
        return df.format('D jS')

    def isoday(self):
        df = DateFormat(self.day)
        return df.format('Y-m-d')


class RegistrationType(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    regtype = models.CharField(max_length=64, null=False, blank=False, verbose_name="Registration type")
    regclass = models.ForeignKey(RegistrationClass, null=True, blank=True, on_delete=models.CASCADE, verbose_name="Registration class")
    cost = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, help_text="Cost excluding VAT.")
    active = models.BooleanField(null=False, blank=False, default=True)
    activeuntil = models.DateField(null=True, blank=True, verbose_name="Active until", help_text="Registration available up to and including this date.")
    inlist = models.BooleanField(null=False, blank=False, default=True)
    sortkey = models.IntegerField(null=False, blank=False, default=10)
    specialtype = models.CharField(max_length=5, blank=True, null=True, choices=special_reg_types, verbose_name="Special type")
    require_phone = models.BooleanField(null=False, blank=False, default=False, help_text="Require phone number to be entered")
    days = models.ManyToManyField(RegistrationDay, blank=True)
    alertmessage = models.TextField(null=False, blank=True, verbose_name="Alert message", help_text="Message shown in popup to user when completing the registration")
    upsell_target = models.BooleanField(null=False, blank=False, default=False, help_text='Is target registration type for upselling in order to add additional options')
    invoice_autocancel_hours = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1), ], verbose_name="Autocancel invoices", help_text="Automatically cancel invoices after this many hours")
    requires_option = models.ManyToManyField('ConferenceAdditionalOption', blank=True, help_text='Requires at least one of the selected additional options to be picked')

    class Meta:
        ordering = ['conference', 'sortkey', ]

    def __str__(self):
        if self.cost == 0:
            return self.regtype
        else:
            return "%s (%s %s)" % (self.regtype,
                                   settings.CURRENCY_ABBREV,
                                   self.total_cost)

    @property
    def total_cost(self):
        if self.conference.vat_registrations:
            return "%.2f incl VAT" % (self.cost * (1 + self.conference.vat_registrations.vatpercent / Decimal(100.0)))
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
        d = dict((a, getattr(self, a) and str(getattr(self, a))) for a in attribs)
        d['regclass'] = self.regclass and self.regclass.safe_export()
        d['days'] = [dd.day.strftime('%Y-%m-%d') for dd in self.days.all()]
        return d

    def validate_object_delete(self):
        # Most deletions are blocked by foreign keys, but registration types are referenced
        # from inside JSON objects in the sponsor system. So build an ugly app-level
        # foreign key...

        # Can't import this model globally as it causes a circular dependency
        from postgresqleu.confsponsor.models import SponsorshipBenefit
        from postgresqleu.confsponsor.benefitclasses import get_benefit_id

        if SponsorshipBenefit.objects.filter(level__conference=self.conference,
                                             benefit_class=get_benefit_id('entryvouchers.EntryVouchers'),
                                             class_parameters__type=self.regtype).exists():
            raise ValidationError("A sponsorship benefit is using this registration type")


class ShirtSize(models.Model):
    shirtsize = models.CharField(max_length=32)
    sortkey = models.IntegerField(default=100, null=False, blank=False)

    def __str__(self):
        return self.shirtsize

    class Meta:
        ordering = ('sortkey', 'shirtsize',)


class ConferenceAdditionalOption(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False, blank=False)
    cost = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, help_text="Cost excluding VAT.")
    maxcount = models.IntegerField(null=False, verbose_name="Maximum number of uses")
    public = models.BooleanField(null=False, blank=False, default=True, help_text='Visible on public forms (opposite of admin only)')
    upsellable = models.BooleanField(null=False, blank=False, default=True, help_text='Can this option be purchased after the registration is completed')
    invoice_autocancel_hours = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(1), ], verbose_name="Autocancel invoices", help_text="Automatically cancel invoices after this many hours")
    requires_regtype = models.ManyToManyField(RegistrationType, blank=True, verbose_name="Requires registration type", help_text='Can only be picked with selected registration types')
    mutually_exclusive = models.ManyToManyField('self', blank=True, help_text='Mutually exlusive with these additional options', symmetrical=True)
    additionaldays = models.ManyToManyField(RegistrationDay, blank=True, verbose_name="Adds access to days", help_text='Adds access to additional conference day(s), even if the registration type does not')

    class Meta:
        ordering = ['name', ]

    def __str__(self):
        # This is what renders in the multichoice checkboxes, so make
        # it nice for the end user.
        if self.cost > 0:
            if self.conference.vat_registrations:
                coststr = " (%s %.2f)" % (settings.CURRENCY_ABBREV, self.cost * (1 + self.conference.vat_registrations.vatpercent / Decimal(100.0)))
            else:
                coststr = " (%s %s)" % (settings.CURRENCY_ABBREV, self.cost)
        else:
            coststr = ""
        if self.maxcount == -1:
            return "%s%s (currently not available)" % (self.name, coststr)
        if self.maxcount > 0:
            usedcount = self.conferenceregistration_set.count() + self.pendingadditionalorder_set.filter(payconfirmedat__isnull=True).count()
            return "%s%s (%s of %s available)" % (self.name, coststr,
                                                  self.maxcount - usedcount,
                                                  self.maxcount)
        return "%s%s" % (self.name, coststr)


class BulkPayment(models.Model):
    # User that owns this bulk payment
    user = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)

    # We attach it to a specific conference
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)

    # Invoice, once one has been created
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE)
    numregs = models.IntegerField(null=False, blank=False)

    createdat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    paidat = models.DateTimeField(null=True, blank=True)

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

    def __str__(self):
        return "Bulk payment for %s created %s (%s registrations, %s%s): %s" % (
            self.conference,
            self.createdat,
            self.numregs,
            settings.CURRENCY_SYMBOL,
            self.invoice.total_amount,
            self.paidat and 'Paid' or 'Not paid yet')


class ConferenceRegistration(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    regtype = models.ForeignKey(RegistrationType, null=True, blank=True, verbose_name="Registration type", on_delete=models.CASCADE)
    attendee = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    registrator = models.ForeignKey(User, null=False, blank=False, related_name="registrator", on_delete=models.CASCADE)
    firstname = models.CharField(max_length=100, null=False, blank=False, verbose_name="First name")
    lastname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Last name")
    email = LowercaseEmailField(null=False, blank=False, verbose_name="E-mail address")
    company = models.CharField(max_length=100, null=False, blank=True, verbose_name="Company")
    address = models.TextField(max_length=200, null=False, blank=True, verbose_name="Address")
    country = models.ForeignKey(Country, null=True, blank=True, verbose_name="Country", on_delete=models.CASCADE)
    phone = models.CharField(max_length=100, null=False, blank=True, verbose_name="Phone number")
    shirtsize = models.ForeignKey(ShirtSize, null=True, blank=True, verbose_name="Preferred T-shirt size", on_delete=models.CASCADE)
    dietary = models.CharField(max_length=100, null=False, blank=True, verbose_name="Special dietary needs")
    additionaloptions = models.ManyToManyField(ConferenceAdditionalOption, blank=True, verbose_name="Additional options")
    twittername = models.CharField(max_length=100, null=False, blank=True, verbose_name="Twitter account", validators=[TwitterValidator, ])
    nick = models.CharField(max_length=100, null=False, blank=True, verbose_name="Nickname")
    badgescan = models.BooleanField(null=False, blank=False, default=True, verbose_name="Allow sponsors get contact information by scanning badge")
    shareemail = models.BooleanField(null=False, blank=False, default=False, verbose_name="Share e-mail address with sponsors")
    photoconsent = models.BooleanField(null=True, blank=False, verbose_name="Consent to having your photo taken at the event by the organisers")
    localoptout = models.BooleanField(null=False, blank=False, default=False, verbose_name="Opt out of emails (when not connected to an account)")

    # Admin fields!
    payconfirmedat = models.DateTimeField(null=True, blank=True, verbose_name="Payment confirmed at")
    payconfirmedby = models.CharField(max_length=16, null=True, blank=True, verbose_name="Payment confirmed by")
    created = models.DateTimeField(null=False, blank=False, verbose_name="Registration created")
    canceledat = models.DateTimeField(null=True, blank=True, verbose_name="Canceled at")
    lastmodified = models.DateTimeField(null=False, blank=False, auto_now=True)
    checkedinat = models.DateTimeField(null=True, blank=True, verbose_name="Checked in at")
    checkedinby = models.ForeignKey('ConferenceRegistration', null=True, blank=True, verbose_name="Checked by by", on_delete=models.CASCADE)

    # If an invoice is generated, link to it here so we can find our
    # way back easily.
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE)
    bulkpayment = models.ForeignKey(BulkPayment, null=True, blank=True, on_delete=models.CASCADE)

    # Any voucher codes. This is just used as temporary storage, and as
    # such we don't try to make it a foreign key. Must be re-validated
    # everytime it's used.
    # It's also used for discount codes - another reason to not use a
    # foreign key :)
    vouchercode = models.CharField(max_length=100, null=False, blank=True, verbose_name='Voucher or discount code')

    # Token to uniquely identify this registration in case we want to
    # access it without a login.
    regtoken = models.TextField(null=False, blank=False, unique=True)
    # Token to identify this user. Only exists for confirmed registrations and is
    # used for example to check in to the conference.
    idtoken = models.TextField(null=False, blank=False, unique=True)
    # Token used to identify this user publicly. This can for example be printed
    # as a QR code on a badge, for others to scan.
    publictoken = models.TextField(null=False, blank=False, unique=True)

    # Messaging configuration
    messaging = models.ForeignKey('ConferenceMessaging', null=True, blank=True, on_delete=models.SET_NULL)
    messaging_copiedfrom = models.ForeignKey(Conference, null=True, blank=True, on_delete=models.SET_NULL, related_name='reg_messaging_copiedfrom')
    messaging_config = models.JSONField(null=False, blank=False, default=dict)

    @property
    def fullname(self):
        return "%s %s" % (self.firstname, self.lastname)

    @property
    def countryname(self):
        if self.country:
            return self.country.name
        else:
            return ''

    def has_invoice(self):
        # Return if this registration has an invoice, whether through
        # a direct invoice or a bulk payment.
        if self.invoice is not None:
            return True
        if self.bulkpayment is not None:
            return True
        return False
    has_invoice.boolean = True

    @property
    def invoice_status(self):
        if self.canceledat:
            return "registration canceled"
        elif self.payconfirmedat:
            return "paid and confirmed"
        elif self.invoice:
            return "invoice generated, not paid"
        elif self.bulkpayment:
            return "bulk invoice generated, not paid"
        else:
            return "pending"

    @property
    def can_edit(self):
        # Can this registration be edited by the end user (which also implies
        # it can be deleted)
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
    def ismultireg(self):
        return self.registrator_id != self.attendee_id

    @property
    def is_volunteer(self):
        return self.volunteers_set.exists()

    @property
    def is_admin(self):
        if self.attendee_id is None:
            return False
        if self.conference.administrators.filter(id=self.attendee_id).exists():
            return True
        return False

    @property
    def is_checkinprocessor(self):
        return self.checkinprocessors_set.exists()

    @cached_property
    def sponsorscanner_token(self):
        qq = self.sponsorscanner_set.all()[:1]
        if qq:
            return qq[0].token
        return None

    @property
    def is_badgescanner(self):
        return self.sponsorscanner_token is not None

    @cached_property
    def is_tweeter(self):
        if self.conference.has_social_broadcast:
            if self.conference.twitter_postpolicy != 0:
                if self.conference.administrators.filter(pk=self.attendee_id).exists():
                    return True
            if self.conference.twitter_postpolicy in (2, 3, 4) and self.is_volunteer:
                return True
        return False

    @property
    def queuepartition(self):
        if self.conference.queuepartitioning == 1:
            k = self.lastname[0].upper()
        elif self.conference.queuepartitioning == 2:
            k = self.firstname[0].upper()
        else:
            return None

        if k >= 'A' and k <= 'Z':
            return k
        return "Other"

    @property
    def payment_method_description(self):
        if not self.payconfirmedat:
            return "Not paid."
        if self.payconfirmedby == "no payment reqd":
            return "Registration does not require payment."
        if self.payconfirmedby == "Multireg/nopay":
            return "Registration is part of multi payment batch that does not require payment."
        if self.payconfirmedby == "Invoice paid":
            if self.invoice:
                return "Paid by individual invoice #{0}.\n Invoice {1}".format(self.invoice.id, self.invoice.payment_method_description)
            else:
                return "Paid by individual invoice, since canceled without refund"
        if self.payconfirmedby == "Bulk paid":
            if self.bulkpayment:
                return "Paid by bulk payment #{0} ({1} total registrations).\n Bulk {2}".format(self.bulkpayment.id, self.bulkpayment.numregs, self.bulkpayment.payment_method_description)
            else:
                return "Paid by bulk payment, which has since been canceled"
        if self.payconfirmedby.startswith("Manual/"):
            return "Manually confirmed"

        return "Payment details not available"

    @property
    def paymenticon(self):
        if self.invoice:
            return 'euro'
        if self.bulkpayment:
            return 'list-alt'
        return 'ban-circle'

    @property
    def alldays(self):
        if self.regtype:
            days = set(self.regtype.days.all())
        else:
            days = set()
        for ao in self.additionaloptions.all():
            days.update(ao.additionaldays.all())
        return sorted(days, key=lambda x: x.day)

    @cached_property
    def access_days(self):
        days = self.alldays

        if not days:
            # Registration days not in use
            return None

        if len(days) == 1:
            return days[0].shortday()

        return ", ".join([x.shortday() for x in days[:-1]]) + " and " + days[-1].shortday()

    @property
    def regdatestr(self):
        days = self.alldays

        if not days:
            return None

        if len(days) == 1:
            return days[0].isoday()

        # If the days are continous, then we list the first and last day
        if all((days[i + 1].day - days[i].day).days == 1 for i in range(len(days) - 1)):
            # Continous range
            return "{} - {}".format(days[0].isoday(), days[-1].isoday())

        return ", ".join([d.isoday() for d in days])

    def get_field_string(self, field):
        r = getattr(self, field)
        if isinstance(r, bool):
            return r and 'Yes' or 'No'
        return getattr(self, field)

    # ID token inluding the identifier
    @property
    def fullidtoken(self):
        if self.idtoken:
            return "{}/t/id/{}/".format(settings.SITEBASE, self.idtoken)
        return ''

    # Public token including the identifier
    @property
    def fullpublictoken(self):
        if self.publictoken:
            return "{}/t/at/{}/".format(settings.SITEBASE, self.publictoken)
        return ''

    # For the admin interface (mainly)
    def __str__(self):
        return "%s: %s %s <%s>" % (self.conference, self.firstname, self.lastname, self.email)

    # For exporting "safe attributes" to external systems
    def safe_export(self):
        attribs = ['firstname', 'lastname', 'email', 'company', 'address', 'country', 'countryname', 'phone', 'shirtsize', 'dietary', 'twittername', 'nick', 'badgescan', 'shareemail', 'fullidtoken', 'fullpublictoken', 'queuepartition', 'alldays', 'regdatestr', 'vouchercode']
        d = dict((a, getattr(self, a) and str(getattr(self, a))) for a in attribs)
        if self.regtype:
            d['regtype'] = self.regtype.safe_export()
        else:
            d['regtype'] = None
        d['additionaloptions'] = [{'id': ao.id, 'name': ao.name} for ao in self.additionaloptions.all()]
        return d


class ConferenceRegistrationLog(models.Model):
    reg = models.ForeignKey(ConferenceRegistration, null=False, blank=False, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    ts = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    txt = models.CharField(max_length=8000, null=False, blank=False)
    changedata = models.CharField(max_length=8000, null=False, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['reg', '-ts']),
        ]


class RegistrationWaitlistEntry(models.Model):
    registration = models.OneToOneField(ConferenceRegistration, primary_key=True, on_delete=models.CASCADE)
    enteredon = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    offeredon = models.DateTimeField(null=True, blank=True)
    offerexpires = models.DateTimeField(null=True, blank=True)

    _safe_attributes = ('enteredon', 'offeredon', 'offerexpires')

    @property
    def offers_made(self):
        return self.registrationwaitlisthistory_set.filter(text__startswith='Made offer').count()


class RegistrationWaitlistHistory(models.Model):
    waitlist = models.ForeignKey(RegistrationWaitlistEntry, null=False, blank=False, on_delete=models.CASCADE)
    time = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    text = models.CharField(max_length=200, null=False, blank=False)

    class Meta:
        ordering = ('-time',)


class Track(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    trackname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Track name")
    color = models.CharField(max_length=20, null=False, blank=True, validators=[color_validator, ], verbose_name="Background color")
    fgcolor = models.CharField(max_length=20, null=False, blank=False, validators=[color_validator, ], verbose_name="Foreground color", default='#000000')
    sortkey = models.IntegerField(null=False, default=100, blank=False)
    incfp = models.BooleanField(null=False, default=False, blank=False, verbose_name="In call for papers")
    insessionlist = models.BooleanField(null=False, default=True, blank=False, verbose_name="In session list")
    showcompany = models.BooleanField(null=False, default=False, blank=False, verbose_name="Show company name",
                                      help_text="Show the company name on the schedule")
    speakerreg = models.BooleanField(null=False, blank=False, default=True, verbose_name="Allow speaker reg",
                                     help_text="Confirmed speakers on this track are allowed to register as speakers, if enabled")

    json_included_attributes = ['trackname', 'color', 'fgcolor', 'sortkey', 'incfp', 'showcompany']

    def __str__(self):
        return self.trackname


class Room(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    roomname = models.CharField(max_length=20, null=False, blank=False, verbose_name="Room name")
    capacity = models.IntegerField(null=True)
    sortkey = models.IntegerField(null=False, blank=False, default=100)
    url = models.URLField(max_length=200, null=False, blank=True, verbose_name='URL',
                          help_text="Link to information about the room")
    comment = models.CharField(max_length=200, null=False, blank=True,
                               help_text='Internal comment for planning')
    availabledays = models.ManyToManyField(RegistrationDay, blank=True, verbose_name='Available days',
                                           help_text='Only used for schedule creation, not actual viewing!')

    json_included_attributes = ['roomname', 'capacity', 'sortkey']

    def __str__(self):
        return self.roomname

    class Meta:
        ordering = ['sortkey', 'roomname', ]


def _get_upload_path(instance, filename):
    return "%s" % instance.id


class Speaker(models.Model):
    user = models.OneToOneField(User, null=True, blank=True, unique=True, on_delete=models.CASCADE)
    fullname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Full name")
    twittername = models.CharField(max_length=32, null=False, blank=True, validators=[TwitterValidator, ],
                                   verbose_name='Twitter name')
    company = models.CharField(max_length=100, null=False, blank=True)
    abstract = models.TextField(null=False, blank=True, verbose_name="Bio")
    photo = ImageBinaryField(blank=True, null=True, verbose_name="Photo (low res)", max_length=1000000, resolution=(128, 128))
    photo512 = ImageBinaryField(blank=True, null=True, verbose_name="Photo", max_length=1000000, resolution=PRIMARY_SPEAKER_PHOTO_RESOLUTION, auto_scale=True)
    lastmodified = models.DateTimeField(auto_now=True, null=False, blank=False)
    speakertoken = models.TextField(null=False, blank=False, unique=True)
    attributes = models.JSONField(blank=True, null=False, default=dict)

    _safe_attributes = ('id', 'name', 'fullname', 'twittername', 'company', 'abstract', 'photo', 'photo512', 'has_photo', 'has_photo512', 'photo_data', 'photo_data512', 'lastmodified', 'attributes')
    json_included_attributes = ['fullname', 'twittername', 'company', 'abstract', 'lastmodified', 'attributes']

    @property
    def name(self):
        return self.fullname

    @property
    def email(self):
        if self.user:
            return self.user.email
        else:
            return None

    def _display_user(self):
        if self.user:
            if self.user.email:
                return "{0} <{1}>".format(self.user.username, self.user.email)
            else:
                return self.user.username

    def has_abstract(self):
        return len(self.abstract) > 0
    has_abstract.boolean = True

    @property
    def has_photo(self):
        return (self.photo is not None and self.photo != "")

    @property
    def has_photo512(self):
        return (self.photo512 is not None and self.photo512 != "")

    @cached_property
    def photo_data(self):
        return base64.b64encode(self.photo).decode('ascii')

    @cached_property
    def photo512_data(self):
        return base64.b64encode(self.photo512).decode('ascii')

    # Legacy compatibility with some old templates
    @property
    def photofile(self):
        return self.photo

    def __str__(self):
        return self.name

    def __reduce_ex__(self, protocol):
        r = super(Speaker, self).__reduce_ex__(protocol)
        # Ooh, this is ugly. But this is to ensure that the 'photo' part of the
        # pickled value works (because memoryviews can't be pickled)
        # NOTE! This appears to have been fixed in Django 3.2.10 (yes, minor release!), thus breaking
        # our fix. So make the fix conditional until we have 3.2.10 everywhere so we can throw it away
        if 'photo' in r[2] and isinstance(r[2]['photo'], memoryview):
            r[2]['photo'] = bytes(r[2]['photo'])
        if 'photo512' in r[2] and isinstance(r[2]['photo512'], memoryview):
            r[2]['photo512'] = bytes(r[2]['photo512'])
        return r

    class Meta:
        ordering = ['fullname', ]


@receiver(pre_save, sender=Speaker)
def _speaker_photo_resizer(sender, instance, *args, **kwargs):
    if instance.photo512:
        instance.photo = rescale_image_bytes(instance.photo512, (128, 128))
    else:
        # If there is a photo, remove it but only if the photo512 entry has actually
        # been deleted (which means it's not NULL anymore)
        if instance.photo and instance.photo512 is not None:
            instance.photo = None


class DeletedItems(models.Model):
    itemid = models.IntegerField(null=False, blank=False)
    type = models.CharField(max_length=16, blank=False, null=False)
    deltime = models.DateTimeField(blank=False, null=False)


class ConferenceSessionScheduleSlot(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    starttime = models.DateTimeField(null=False, blank=False, verbose_name="Start time")
    endtime = models.DateTimeField(null=False, blank=False, verbose_name="End time")

    def __str__(self):
        return "%s - %s" % (self.starttime, self.endtime)


class ConferenceSessionTag(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    tag = models.CharField(max_length=32, null=False, blank=False)
    slug = models.CharField(max_length=32, null=False, blank=False)

    def __str__(self):
        return self.tag

    def save(self, *args, **kwargs):
        self.slug = slugify(self.tag)
        super(ConferenceSessionTag, self).save(*args, **kwargs)

    class Meta:
        unique_together = (
            ('conference', 'tag'),
            ('conference', 'slug'),
        )


class ConferenceSession(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    speaker = models.ManyToManyField(Speaker, blank=True, verbose_name="Speakers")
    title = models.CharField(max_length=200, null=False, blank=False)
    starttime = models.DateTimeField(null=True, blank=True)
    endtime = models.DateTimeField(null=True, blank=True)
    track = models.ForeignKey(Track, null=True, blank=True, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.CASCADE)
    cross_schedule = models.BooleanField(null=False, default=False)
    can_feedback = models.BooleanField(null=False, default=True)
    abstract = models.TextField(null=False, blank=True)
    skill_level = models.IntegerField(null=False, default=1, choices=SKILL_CHOICES)
    htmlicon = models.CharField(max_length=100, null=False, blank=True, verbose_name="HTML Icon", help_text="HTML representing an icon used for this session on the schedule (and optionally elsewhere)")
    status = models.IntegerField(null=False, default=0, choices=STATUS_CHOICES)
    lastnotifiedstatus = models.IntegerField(null=False, default=0, choices=STATUS_CHOICES)
    lastnotifiedtime = models.DateTimeField(null=True, blank=True, verbose_name="Notification last sent")
    submissionnote = models.TextField(null=False, blank=True, verbose_name="Submission notes")
    internalnote = models.TextField(null=False, blank=True, verbose_name="Internal notes")
    initialsubmit = models.DateTimeField(null=True, blank=True, verbose_name="Submitted")
    tentativescheduleslot = models.ForeignKey(ConferenceSessionScheduleSlot, null=True, blank=True, on_delete=models.CASCADE)
    tentativeroom = models.ForeignKey(Room, null=True, blank=True, related_name='tentativeroom', on_delete=models.CASCADE)
    lastmodified = models.DateTimeField(auto_now=True, null=False, blank=False)
    reminder_sent = models.BooleanField(null=False, default=False, verbose_name='Speaker reminder(s) sent')
    tags = models.ManyToManyField(ConferenceSessionTag, blank=True)

    # NOTE! Any added fields need to be considered for inclusion in
    # forms.CallForPapersForm and in views.callforpapers_copy()!

    # Not a db field, but set from the view to track if the current user
    # has given any feedback on this session.
    has_given_feedback = False

    @property
    def speaker_list(self):
        if self.id:
            return ", ".join([s.name for s in self.speaker.all()])
        else:
            return "<none>"

    @property
    def skill_level_string(self):
        return next((t for v, t in SKILL_CHOICES if v == self.skill_level))

    @property
    def status_string(self):
        return get_status_string(self.status)

    @property
    def status_string_long(self):
        return get_status_string_long(self.status)

    @property
    def status_string_short(self):
        return get_status_string_short(self.status)

    @property
    def lastnotified_status_string(self):
        return get_status_string(self.lastnotifiedstatus)

    @property
    def lastnotified_status_string_long(self):
        return get_status_string_long(self.lastnotifiedstatus)

    @property
    def has_feedback(self):
        return self.conferencesessionfeedback_set.exists()

    def __str__(self):
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

    class Meta:
        ordering = ['starttime', ]


class ConferenceSessionSlides(models.Model):
    session = models.ForeignKey(ConferenceSession, null=False, blank=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False, blank=False)
    url = models.URLField(max_length=1000, null=False, blank=True, verbose_name='URL')
    content = PdfBinaryField(null=True, blank=True, max_length=20000000000, verbose_name='Upload PDF')

    _safe_attributes = ('id', 'name', 'url', 'content')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('session', 'name', )


class ConferenceSessionVote(models.Model):
    session = models.ForeignKey(ConferenceSession, null=False, blank=False, on_delete=models.CASCADE)
    voter = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    vote = models.IntegerField(null=True, blank=False)
    comment = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = (('session', 'voter',), )


class ConferenceSessionFeedback(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    session = models.ForeignKey(ConferenceSession, null=False, blank=False, on_delete=models.CASCADE)
    attendee = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    topic_importance = models.IntegerField(null=False, blank=False)
    content_quality = models.IntegerField(null=False, blank=False)
    speaker_knowledge = models.IntegerField(null=False, blank=False)
    speaker_quality = models.IntegerField(null=False, blank=False)
    speaker_feedback = models.TextField(null=False, blank=True, verbose_name='Comments to the speaker')
    conference_feedback = models.TextField(null=False, blank=True, verbose_name='Comments to the conference organizers')

    def __str__(self):
        return str("%s - %s (%s)") % (self.conference, self.session, self.attendee)


class ConferenceFeedbackQuestion(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    question = models.CharField(max_length=100, null=False, blank=False)
    isfreetext = models.BooleanField(blank=False, null=False, default=False, verbose_name='Text field',
                                     help_text='Text field (instead of rate 1-5)')
    textchoices = models.CharField(max_length=500, null=False, blank=True, verbose_name='Text choices')
    sortkey = models.IntegerField(null=False, default=100, verbose_name='Sort key')
    newfieldset = models.CharField(max_length=100, null=False, blank=True,
                                   verbose_name='Start new fieldset')

    def __str__(self):
        return "%s: %s" % (self.conference, self.question)

    class Meta:
        ordering = ['conference', 'sortkey', ]


class ConferenceFeedbackAnswer(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    question = models.ForeignKey(ConferenceFeedbackQuestion, null=False, blank=False, on_delete=models.CASCADE)
    attendee = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    rateanswer = models.IntegerField(null=True)
    textanswer = models.TextField(null=False, blank=True)

    def __str__(self):
        return "%s - %s: %s" % (self.conference, self.attendee, self.question.question)

    class Meta:
        ordering = ['conference', 'attendee', 'question', ]


class VolunteerSlot(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    timerange = DateTimeRangeField(null=False, blank=False)
    title = models.CharField(max_length=50, null=False, blank=False)
    min_staff = models.IntegerField(null=False, blank=False, default=1, validators=[MinValueValidator(1)])
    max_staff = models.IntegerField(null=False, blank=False, default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ['timerange', ]

    def __str__(self):
        return self._display_timerange()

    def _display_timerange(self):
        start = timezone.localtime(self.timerange.lower)
        end = timezone.localtime(self.timerange.upper)
        if start.date() == end.date():
            return "{0} - {1}".format(
                DateFormat(start).format(settings.DATETIME_FORMAT),
                DateFormat(end).format(settings.TIME_FORMAT),
            )
        else:
            return "{0} - {1}".format(
                DateFormat(start).format(settings.DATETIME_FORMAT),
                DateFormat(end).format(settings.DATETIME_FORMAT),
            )

    @property
    def countvols(self):
        return self.volunteerassignment_set.all().count()

    @property
    def weekday(self):
        return timezone.localtime(self.timerange.lower).strftime('%Y-%m-%d (%A)')


class VolunteerAssignment(models.Model):
    slot = models.ForeignKey(VolunteerSlot, null=False, blank=False, on_delete=models.CASCADE)
    reg = models.ForeignKey(ConferenceRegistration, null=False, blank=False, on_delete=models.CASCADE)
    vol_confirmed = models.BooleanField(null=False, blank=False, default=False, verbose_name="Confirmed by volunteer")
    org_confirmed = models.BooleanField(null=False, blank=False, default=False, verbose_name="Confirmed by organizers")
    reminder_sent = models.BooleanField(null=False, default=False, verbose_name='Volunteer reminder(s) sent')

    _safe_attributes = ('id', 'slot', 'reg', 'vol_confirmed', 'org_confirmed')


class PrepaidBatch(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    regtype = models.ForeignKey(RegistrationType, null=False, blank=False, on_delete=models.CASCADE)
    buyer = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    buyername = models.CharField(max_length=100, null=True, blank=True)
    sponsor = models.ForeignKey('confsponsor.Sponsor', null=True, blank=True, verbose_name="Optional sponsor", on_delete=models.CASCADE)

    def __str__(self):
        return "%s: %s for %s" % (self.conference, self.regtype, self.buyer)

    class Meta:
        verbose_name_plural = "Prepaid batches"
        ordering = ['conference', 'id', ]


class PrepaidVoucher(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    vouchervalue = models.CharField(max_length=100, null=False, blank=False, unique=True)
    batch = models.ForeignKey(PrepaidBatch, null=False, blank=False, on_delete=models.CASCADE)
    user = models.ForeignKey(ConferenceRegistration, null=True, blank=True, on_delete=models.CASCADE)
    usedate = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.vouchervalue

    class Meta:
        ordering = ['batch', 'vouchervalue', ]


class DiscountCode(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    code = models.CharField(max_length=100, null=False, blank=False)
    discountamount = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, verbose_name="Discount amount")
    discountpercentage = models.IntegerField(null=False, blank=False, default=0, verbose_name="Discount percentage")
    regonly = models.BooleanField(null=False, blank=False, default=False, verbose_name="Registration only", help_text="Apply percentage discount only to the registration cost, not additional options. By default, it's applied to both.")
    validuntil = models.DateField(blank=True, null=True, verbose_name="Valid until", help_text="Valid up to and including this date.")
    maxuses = models.IntegerField(null=False, blank=False, default=0, verbose_name="Max uses")
    requiresoption = models.ManyToManyField(ConferenceAdditionalOption, blank=True, verbose_name="Requires option", help_text='Requires this option to be set in order to be valid')
    requiresregtype = models.ManyToManyField(RegistrationType, blank=True, verbose_name="Requires registration type", help_text='Require a specific registration type to be valid')
    public = models.BooleanField(null=False, blank=False, default=False, help_text="Is the existance of this discount code public")

    registrations = models.ManyToManyField(ConferenceRegistration, blank=True)

    # If this discount code is purchased by a sponsor, track it here.
    sponsor = models.ForeignKey('confsponsor.Sponsor', null=True, blank=True, verbose_name="Optional sponsor.", help_text="Note that if a sponsor is picked, an invoice will be generated once the discount code closes!!!", on_delete=models.CASCADE)
    sponsor_rep = models.ForeignKey(User, null=True, blank=True, verbose_name="Optional sponsor representative.", help_text="Must be set if the sponsor field is set!", on_delete=models.CASCADE)
    is_invoiced = models.BooleanField(null=False, blank=False, default=False, verbose_name="Has an invoice been sent for this discount code.")

    def __str__(self):
        return self.code

    class Meta:
        unique_together = (('conference', 'code',), )
        ordering = ('conference', 'code',)

    @property
    def count(self):
        return self.registrations.count()


class SavedReportDefinition(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, null=False, blank=False)
    definition = models.JSONField(blank=False, null=False, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ('title', )
        unique_together = (
            ('conference', 'title'),
        )


class AttendeeMail(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    regclasses = models.ManyToManyField(RegistrationClass, blank=True, verbose_name="Registration classes")
    registrations = models.ManyToManyField(ConferenceRegistration, blank=True, verbose_name="Registrations")
    pending_regs = models.ManyToManyField(User, blank=True, verbose_name="Pending registrations")
    tovolunteers = models.BooleanField(null=False, blank=False, default=False, verbose_name="To volunteers")
    tocheckin = models.BooleanField(null=False, blank=False, default=False, verbose_name="To check-in processors")
    addopts = models.ManyToManyField(ConferenceAdditionalOption, blank=True, verbose_name="Attendees with options")
    sentat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    subject = models.CharField(max_length=100, null=False, blank=False)
    message = models.TextField(max_length=8000, null=False, blank=False)

    def __str__(self):
        return "%s: %s" % (timezone.localtime(self.sentat).strftime("%Y-%m-%d %H:%M"), self.subject)

    class Meta:
        ordering = ('-sentat', )


class PendingAdditionalOrder(models.Model):
    reg = models.ForeignKey(ConferenceRegistration, null=False, blank=False, on_delete=models.CASCADE)
    options = models.ManyToManyField(ConferenceAdditionalOption, blank=False)
    newregtype = models.ForeignKey(RegistrationType, null=True, blank=True, on_delete=models.CASCADE)
    createtime = models.DateTimeField(null=False, blank=False)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE)
    payconfirmedat = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "%s" % (self.reg, )

    @property
    def invoice_status(self):
        if self.payconfirmedat:
            return "paid and confirmed"
        elif self.invoice:
            return "invoice generated, not paid"
        else:
            return "pending"


class RefundPattern(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    percent = models.IntegerField(null=False, verbose_name="Percent to refund", validators=[MinValueValidator(1), MaxValueValidator(100)])
    fees = models.DecimalField(decimal_places=2, max_digits=10, null=False, verbose_name="Fees not to refund", help_text="This amount will be deducted from the calculated refund amount. Amount should be entered *without* VAT.")
    fromdate = models.DateField(null=True, blank=True, verbose_name="From date", help_text="Suggest for refunds starting from this date")
    todate = models.DateField(null=True, blank=True, verbose_name="To date", help_text="Suggest for refunds until this date")


class AggregatedTshirtSizes(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    size = models.ForeignKey(ShirtSize, null=False, blank=False, on_delete=models.CASCADE)
    num = models.IntegerField(null=False, blank=False)

    class Meta:
        unique_together = (('conference', 'size'), )


class AggregatedDietary(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    dietary = models.CharField(max_length=100, null=False, blank=False)
    num = models.IntegerField(null=False, blank=False)

    class Meta:
        unique_together = (('conference', 'dietary'), )


AccessTokenPermissions = (
    ('regtypes', 'Registration types and counters'),
    ('discounts', 'Discount codes'),
    ('discountspublic', 'Public discount codes'),
    ('vouchers', 'Voucher codes'),
    ('sponsors', 'Sponsors and counts'),
    ('addopts', 'Additional options and counts'),
    ('schedule', 'Schedule JSON'),
)


class AccessToken(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    token = models.CharField(max_length=200, null=False, blank=False)
    description = models.TextField(null=False, blank=False)
    permissions = ChoiceArrayField(
        models.CharField(max_length=32, blank=False, null=False, choices=AccessTokenPermissions)
    )

    class Meta:
        unique_together = (('conference', 'token'), )

    def __str__(self):
        return self.token

    def _display_permissions(self):
        return ", ".join(self.permissions)


class ConferenceNews(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    datetime = models.DateTimeField(blank=False, default=timezone.now)
    title = models.CharField(max_length=128, blank=False)
    summary = models.TextField(blank=False)
    author = models.ForeignKey(NewsPosterProfile, on_delete=models.CASCADE)
    inrss = models.BooleanField(null=False, default=True, verbose_name="Include in RSS feed")
    tweeted = models.BooleanField(null=False, blank=False, default=False)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-datetime', ]
        verbose_name_plural = 'Conference News'

    _safe_attributes = ('id', 'datetime', 'title', 'summary', 'author', 'inrss')


class ConferenceHashtag(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    hashtag = models.CharField(max_length=32, null=False, blank=False,
                               validators=[RegexValidator('^[#@]', 'Enter a hashtag (starting with #) or username (starting with @)'), ])

    def __str__(self):
        return self.hashtag

    class Meta:
        unique_together = (
            ('conference', 'hashtag', )
        )
        ordering = ['hashtag', ]


class MessagingProvider(models.Model):
    series = models.ForeignKey(ConferenceSeries, null=True, blank=True, on_delete=models.CASCADE)
    internalname = models.CharField(max_length=100, null=False, blank=False, verbose_name='Internal name')
    publicname = models.CharField(max_length=100, null=False, blank=False, verbose_name='Public name')
    classname = models.CharField(max_length=200, null=False, blank=False, verbose_name="Implementation class")
    active = models.BooleanField(null=False, blank=False, default=False)
    config = models.JSONField(blank=False, null=False, default=dict, encoder=DjangoJSONEncoder)
    route_incoming = models.ForeignKey(Conference, null=True, blank=True, verbose_name="Route incoming messages to", on_delete=models.SET_NULL, related_name='incoming_messaging_route_for')
    private_checkpoint = models.BigIntegerField(null=False, blank=False, default=0)
    private_lastpoll = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    public_checkpoint = models.BigIntegerField(null=False, blank=False, default=0)
    public_lastpoll = models.DateTimeField(null=False, blank=False, auto_now_add=True)

    def __str__(self):
        return self.internalname

    class Meta:
        ordering = ('internalname', )


class ConferenceMessaging(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    provider = models.ForeignKey(MessagingProvider, null=False, blank=False, on_delete=models.CASCADE)

    broadcast = models.BooleanField(null=False, blank=False, default=False, verbose_name='Broadcasts')
    privatebcast = models.BooleanField(null=False, blank=False, default=False, verbose_name='Attendee only broadcasts')
    notification = models.BooleanField(null=False, blank=False, default=False, verbose_name='Private notifications')
    orgnotification = models.BooleanField(null=False, blank=False, default=False, verbose_name='Organizer notifications')
    socialmediamanagement = models.BooleanField(null=False, blank=False, default=False, verbose_name='Social media management')
    config = models.JSONField(blank=False, null=False, default=dict)

    class Meta:
        verbose_name = 'messaging configuration'
        ordering = ('provider__publicname', )
        unique_together = (
            ('conference', 'provider'),
        )

    def __str__(self):
        return self.provider.publicname

    @property
    def full_info(self):
        if self.notification and self.privatebcast:
            return "{} - personal notifications and announcements".format(self)
        elif self.notification:
            return "{} - personal notifications only".format(self)
        elif self.privatebcast:
            return "{} - announcements only".format(self)
        else:
            return str(self)


class ConferenceTweetQueue(models.Model):
    conference = models.ForeignKey(Conference, null=True, on_delete=models.CASCADE)
    datetime = models.DateTimeField(blank=False, default=timezone.now, verbose_name="Date and time",
                                    help_text="Date and time to send tweet")
    contents = models.CharField(max_length=1000, null=False, blank=False)
    image = ImageBinaryField(null=True, blank=True, max_length=1000000)
    imagethumb = ImageBinaryField(null=True, blank=True, max_length=100000)
    approved = models.BooleanField(null=False, default=False, blank=False)
    author = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    approvedby = models.ForeignKey(User, null=True, blank=True, related_name="tweetapprovals", on_delete=models.CASCADE)
    sent = models.BooleanField(null=False, default=False, blank=False)
    postids = models.JSONField(null=False, blank=False, default=dict)
    replytotweetid = models.BigIntegerField(null=True, blank=True, verbose_name="Reply to tweet")
    remainingtosend = models.ManyToManyField(MessagingProvider, blank=True)
    comment = models.CharField(max_length=200, null=False, blank=True, verbose_name="Internal comment")
    metadata = models.JSONField(null=False, blank=False, default=dict)

    class Meta:
        ordering = ['sent', 'datetime', ]
        verbose_name_plural = 'Conference Tweets'
        verbose_name = 'Conference Tweet'
        indexes = [
            GinIndex(name='tweetqueue_postids_idx', fields=['postids'], opclasses=['jsonb_path_ops']),
            GinIndex(name='tweetqueue_metadata_idx', fields=['metadata'], opclasses=['jsonb_path_ops']),
            models.Index(fields=['conference', '-datetime']),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # When we are saving, *if* we have not yet been sent, materialize a list of
        # which providers to send to. However, we *only* do this if there isn't something
        # already in the list to be remaining -- if there is, then we just keep adding things
        # back that have already been taken care of.
        if self.approved and not self.sent and not self.remainingtosend.exists():
            if self.conference:
                self.remainingtosend.set(MessagingProvider.objects.filter(active=True, conferencemessaging__conference=self.conference, conferencemessaging__broadcast=True))
            else:
                self.remainingtosend.set(MessagingProvider.objects.filter(active=True, series__isnull=True))
            exec_no_result("NOTIFY pgeu_broadcast")


class ConferenceIncomingTweet(models.Model):
    conference = models.ForeignKey(Conference, null=False, on_delete=models.CASCADE)
    provider = models.ForeignKey(MessagingProvider, null=True, on_delete=models.SET_NULL)
    statusid = models.BigIntegerField(null=False, blank=False)
    created = models.DateTimeField(null=False, blank=False)
    processedat = models.DateTimeField(null=True, blank=True)
    processedby = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    text = models.CharField(max_length=512, null=False, blank=False)
    replyto_statusid = models.BigIntegerField(null=True, blank=True, db_index=True)
    author_id = models.BigIntegerField(null=False, blank=False)
    author_screenname = models.CharField(max_length=50, null=False, blank=False)
    author_name = models.CharField(max_length=100, null=False, blank=False)
    author_image_url = models.URLField(max_length=1024, null=False, blank=False)
    quoted_statusid = models.BigIntegerField(null=True, blank=True)
    quoted_text = models.CharField(max_length=512, null=True, blank=True)
    quoted_permalink = models.URLField(max_length=1024, null=True, blank=True)
    retweetstate = models.IntegerField(null=False, blank=False, default=0, choices=((0, 'No retweet'), (1, 'Scheduled'), (2, 'Retweeted')))

    class Meta:
        unique_together = (
            ('statusid', 'provider'),
        )


class ConferenceIncomingTweetMedia(models.Model):
    incomingtweet = models.ForeignKey(ConferenceIncomingTweet, null=False, blank=False, on_delete=models.CASCADE)
    sequence = models.IntegerField(null=False, blank=False)
    mediaurl = models.URLField(max_length=1024, null=False, blank=False)

    class Meta:
        unique_together = (
            ('incomingtweet', 'sequence'),
        )


# Either reg *or* channel is set!
class NotificationQueue(models.Model):
    time = models.DateTimeField(null=False, blank=False)
    expires = models.DateTimeField(null=False, blank=False)
    messaging = models.ForeignKey(ConferenceMessaging, null=False, blank=False, on_delete=models.CASCADE)
    reg = models.ForeignKey(ConferenceRegistration, null=True, blank=True, on_delete=models.CASCADE)
    channel = models.CharField(max_length=50, null=True, blank=True)
    msg = models.TextField(null=False, blank=False)


class IncomingDirectMessage(models.Model):
    provider = models.ForeignKey(MessagingProvider, null=False, blank=False, on_delete=models.CASCADE)
    time = models.DateTimeField(null=False, blank=False)
    postid = models.BigIntegerField(null=False, blank=False)
    internallyprocessed = models.BooleanField(null=False, blank=False, default=False)
    sender = models.JSONField(null=False, blank=False, default=dict)
    txt = models.TextField(null=False, blank=True)

    class Meta:
        unique_together = (
            ('postid', 'provider', ),
        )


class CrossConferenceEmail(models.Model):
    sentat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    sentby = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    senderaddr = LowercaseEmailField(null=False, blank=False, verbose_name='Sender address')
    sendername = models.CharField(max_length=100, null=False, blank=False, verbose_name='Sender name')
    subject = models.CharField(max_length=80, null=False, blank=False)
    text = models.TextField(blank=False, null=False)

    @property
    def rules_included(self):
        return CrossConferenceEmailRule.objects.filter(email=self, isexclude=False)

    @property
    def rules_excluded(self):
        return CrossConferenceEmailRule.objects.filter(email=self, isexclude=True)


class CrossConferenceEmailRule(models.Model):
    email = models.ForeignKey(CrossConferenceEmail, null=False, blank=False, on_delete=models.CASCADE)
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    isexclude = models.BooleanField(null=False, blank=False)
    ruletype = models.CharField(max_length=10, null=False, blank=False)
    ruleref = models.IntegerField(null=False, blank=False)
    canceled = models.BooleanField(null=False)

    @property
    def displaystr(self):
        if self.ruletype == 'rt':
            if self.ruleref == -1:
                ruledetails = 'All registrations'
            else:
                ruledetails = 'Registrations of type {}'.format(RegistrationType.objects.get(conference=self.conference, id=self.ruleref).regtype)

        elif self.ruletype == 'sp':
            if self.ruleref == -1:
                ruledetails = 'All speakers'
            elif self.ruleref == -2:
                ruledetails = 'All speakers with sessions in status accepted and reserve'
            else:
                ruledetails = 'Speakers with sessions in status {}'.format(get_status_string(self.ruleref))
        else:
            return 'Unknown rule type'

        if self.canceled:
            ruledetails += ' (including canceled registrations)'

        return "{}: {}".format(
            self.conference,
            ruledetails,
        )


class CrossConferenceEmailRecipient(models.Model):
    email = models.ForeignKey(CrossConferenceEmail, null=False, blank=False, on_delete=models.CASCADE)
    address = LowercaseEmailField(null=False, blank=False)

    class Meta:
        unique_together = (
            ('email', 'address'),
        )


class ConferenceRegistrationTemporaryToken(models.Model):
    reg = models.OneToOneField(ConferenceRegistration, null=False, blank=False, unique=True, on_delete=models.CASCADE)
    token = models.TextField(null=False, blank=False, unique=True)
    expires = models.DateTimeField(null=False, blank=False)
