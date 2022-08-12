from django.db import models
from django.utils.functional import cached_property
from django.contrib.auth.models import User
from django.utils import timezone

from postgresqleu.confreg.models import Conference, RegistrationType, PrepaidBatch
from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.util.fields import PdfBinaryField
from postgresqleu.util.validators import validate_lowercase, validate_urlname
from postgresqleu.util.random import generate_random_token

from .benefits import benefit_choices

vat_status_choices = (
    (0, 'Company is from inside EU and has VAT number'),
    (1, 'Company is from inside EU, but does not have VAT number'),
    (2, 'Company is from outside EU'),
)


class SponsorshipContract(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    contractname = models.CharField(max_length=100, null=False, blank=False, verbose_name='Contract name')
    contractpdf = PdfBinaryField(null=False, blank=False, max_length=1000000)

    def __str__(self):
        return self.contractname


class SponsorshipLevel(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    levelname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Level name")
    urlname = models.CharField(max_length=100, null=False, blank=False,
                               validators=[validate_lowercase, validate_urlname],
                               verbose_name="URL name")
    levelcost = models.IntegerField(null=False, blank=False, verbose_name="Cost")
    available = models.BooleanField(null=False, blank=False, default=True, verbose_name="Available for signup")
    public = models.BooleanField(null=False, blank=False, default=True, verbose_name="Publicly visible",
                                 help_text="If unchecked the sponsorship level will be treated as internal, for example for testing")
    maxnumber = models.IntegerField(null=False, blank=False, default=0, verbose_name="Maximum number of sponsors")
    instantbuy = models.BooleanField(null=False, blank=False, default=False, verbose_name="Instant buy available")
    paymentmethods = models.ManyToManyField(InvoicePaymentMethod, blank=False, verbose_name="Payment methods for generated invoices")
    contract = models.ForeignKey(SponsorshipContract, blank=True, null=True, on_delete=models.CASCADE)
    canbuyvoucher = models.BooleanField(null=False, blank=False, default=True, verbose_name="Can buy vouchers")
    canbuydiscountcode = models.BooleanField(null=False, blank=False, default=True, verbose_name="Can buy discount codes")

    def __str__(self):
        return self.levelname

    class Meta:
        ordering = ('-levelcost', 'levelname',)
        unique_together = (('conference', 'urlname'), )

    @cached_property
    def num_confirmed(self):
        return self.sponsor_set.filter(confirmed=True).count()

    @cached_property
    def num_unconfirmed(self):
        return self.sponsor_set.filter(confirmed=False).count()

    @cached_property
    def num_total(self):
        return self.num_confirmed + self.num_unconfirmed

    @cached_property
    def can_signup(self):
        if self.available:
            if self.maxnumber > 0:
                return self.num_confirmed < self.maxnumber
            else:
                return True
        return False


class SponsorshipBenefit(models.Model):
    level = models.ForeignKey(SponsorshipLevel, null=False, blank=False, on_delete=models.CASCADE)
    benefitname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Benefit name")
    sortkey = models.PositiveIntegerField(null=False, blank=False, default=100, verbose_name="Sort key")
    benefitdescription = models.TextField(null=False, blank=True, verbose_name="Benefit description")
    claimprompt = models.TextField(null=False, blank=True, verbose_name="Claim prompt")
    benefit_class = models.IntegerField(null=True, blank=True, default=None, choices=benefit_choices)
    class_parameters = models.JSONField(blank=True, null=False)
    tweet_template = models.TextField(null=False, blank=True)

    def __str__(self):
        return self.benefitname

    class Meta:
        ordering = ('sortkey', 'benefitname', )


class Sponsor(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False, blank=False)
    displayname = models.CharField(max_length=100, null=False, blank=False, verbose_name='Display name')
    invoiceaddr = models.TextField(max_length=500, null=False, blank=True, verbose_name='Invoice address')
    vatstatus = models.IntegerField(null=True, blank=False, choices=vat_status_choices, verbose_name='VAT status')
    vatnumber = models.CharField(max_length=100, null=True, blank=True, verbose_name='VAT number')
    managers = models.ManyToManyField(User, blank=False)
    url = models.URLField(max_length=200, null=False, blank=True)
    twittername = models.CharField(max_length=100, null=False, blank=True)
    level = models.ForeignKey(SponsorshipLevel, null=False, blank=False, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE)
    confirmed = models.BooleanField(null=False, blank=False, default=False)
    confirmedat = models.DateTimeField(null=True, blank=True)
    confirmedby = models.CharField(max_length=50, null=False, blank=True)
    signupat = models.DateTimeField(null=False, blank=False)
    extra_cc = models.EmailField(null=False, blank=True, verbose_name="Extra information address")

    def __str__(self):
        return self.name

    _safe_attributes = ('id', 'displayname', 'twittername', 'url', )


class SponsorClaimedBenefit(models.Model):
    sponsor = models.ForeignKey(Sponsor, null=False, blank=False, on_delete=models.CASCADE)
    benefit = models.ForeignKey(SponsorshipBenefit, null=False, blank=False, on_delete=models.CASCADE)
    claimedat = models.DateTimeField(null=False, blank=False)
    claimedby = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    declined = models.BooleanField(null=False, blank=False, default=False)
    claimjson = models.JSONField(blank=True, null=False)
    confirmed = models.BooleanField(null=False, blank=False, default=False)

    class Meta:
        unique_together = (('sponsor', 'benefit'),)


class SponsorMail(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    levels = models.ManyToManyField(SponsorshipLevel, blank=True)
    sponsors = models.ManyToManyField(Sponsor, blank=True)
    sentat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    subject = models.CharField(max_length=100, null=False, blank=False)
    message = models.TextField(max_length=8000, null=False, blank=False)

    def __str__(self):
        return "%s: %s" % (timezone.localtime(self.sentat).strftime("%Y-%m-%d %H:%M"), self.subject)

    class Meta:
        ordering = ('-sentat',)


class SponsorScanner(models.Model):
    sponsor = models.ForeignKey(Sponsor, null=False, blank=False, on_delete=models.CASCADE)
    scanner = models.ForeignKey(ConferenceRegistration, null=False, blank=False, on_delete=models.CASCADE)
    token = models.TextField(null=False, blank=False, unique=True)

    class Meta:
        unique_together = (
            ('sponsor', 'scanner', ),
        )

    _safe_attributes = ('id', 'sponsor', 'token', )


class ScannedAttendee(models.Model):
    sponsor = models.ForeignKey(Sponsor, null=False, blank=False, on_delete=models.CASCADE)
    scannedby = models.ForeignKey(ConferenceRegistration, null=False, blank=False, related_name='scanned_attendees', on_delete=models.CASCADE)
    attendee = models.ForeignKey(ConferenceRegistration, null=False, blank=False, related_name='scanned_by', on_delete=models.CASCADE)
    scannedat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    note = models.TextField(null=False, blank=True)

    class Meta:
        ordering = ('-scannedat', )
        unique_together = (
            ('sponsor', 'scannedby', 'attendee', )
        )

    _safe_attributes = ('sponsor', 'scannedat', )


class PurchasedVoucher(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    sponsor = models.ForeignKey(Sponsor, null=True, blank=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    regtype = models.ForeignKey(RegistrationType, null=False, blank=False, on_delete=models.CASCADE)
    num = models.IntegerField(null=False, blank=False)
    invoice = models.ForeignKey(Invoice, null=False, blank=False, on_delete=models.CASCADE)
    batch = models.OneToOneField(PrepaidBatch, null=True, blank=True, on_delete=models.CASCADE)


class ShipmentAddress(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    available_to = models.ManyToManyField(SponsorshipLevel, blank=True,
                                          help_text="Which sponsorsihp levels is this address available to")
    active = models.BooleanField(null=False, blank=False, default=False,
                                 help_text="Can address be viewed?")
    startdate = models.DateField(null=True, blank=True,
                                 help_text="Shipments cannot arrive before")
    enddate = models.DateField(null=True, blank=True,
                               help_text="Shipments cannot arrive after")
    token = models.TextField(null=False, blank=False, unique=True,
                             help_text="Token used by arriving party to indicate shipments",
                             default=generate_random_token)
    title = models.CharField(max_length=100, null=False, blank=False)
    address = models.TextField(null=False, blank=False)
    description = models.TextField(null=False, blank=True)

    _safe_attributes = ('active', 'startdate', 'enddate', 'token',
                        'title', 'address', 'description')

    class Meta:
        ordering = ('startdate', 'enddate', 'title', )


class Shipment(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    sponsor = models.ForeignKey(Sponsor, null=True, blank=True, on_delete=models.CASCADE)
    address = models.ForeignKey(ShipmentAddress, null=False, blank=False, on_delete=models.CASCADE)
    addresstoken = models.BigIntegerField(null=False, blank=False)
    description = models.CharField(max_length=200, null=False, blank=False)
    sent_parcels = models.IntegerField(null=False, blank=False,
                                       help_text="Number of parcels sent",
                                       verbose_name="Parcel count")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Shipment sent at")
    arrived_at = models.DateTimeField(null=True, blank=True,
                                      help_text="Parcels arrived at")
    arrived_parcels = models.IntegerField(null=False, blank=False,
                                          help_text="Number of parcels arrived")
    trackingnumber = models.CharField(max_length=100, null=False, blank=True,
                                      verbose_name="Tracking number")
    shippingcompany = models.CharField(max_length=100, null=False, blank=True,
                                       verbose_name="Shipping company")
    trackinglink = models.URLField(max_length=200, null=False, blank=True,
                                   verbose_name="Tracking link")

    _safe_attributes = ('sponsor', 'address', 'addresstoken', 'description',
                        'sent_parcels', 'sent_at', 'arrived_at', 'arrived_parcels',
                        'trackingnumber', 'shippingcompany', 'trackinglink', )

    class Meta:
        unique_together = (
            ('conference', 'addresstoken'),
        )

    @property
    def full_address(self):
        return self.address.address.replace('%%', str(self.addresstoken))

    @property
    def status_label_class(self):
        if self.sent_at is None:
            # Not sent yet
            return "warning"
        if self.arrived_at is not None:
            # Has arrived. Check the number of parcels.
            # They must be the same, or if sent parcels is set to 0 = Unknown,
            # we just ignore it.
            if self.arrived_parcels == self.sent_parcels or self.sent_parcels == 0:
                return "success"
            else:
                return "danger"

        return ""

    @property
    def sender(self):
        if self.sponsor:
            return self.sponsor.name
        return "{0} organizers".format(self.conference)
