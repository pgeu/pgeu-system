from django.db import models
from django.db.models.signals import pre_delete
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField

from postgresqleu.confreg.models import Conference, RegistrationType, PrepaidBatch
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.util.storage import InlineEncodedStorage
from postgresqleu.util.storage import delete_inline_storage, inlineencoded_upload_path
from postgresqleu.util.validators import validate_lowercase

from benefits import benefit_choices

from django.db.models import FileField

vat_status_choices = (
    (0, 'Company is from inside EU and has VAT number'),
    (1, 'Company is from inside EU, but does not have VAT number'),
    (2, 'Company is from outside EU'),
)

class SponsorshipContract(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    contractname = models.CharField(max_length=100, null=False, blank=False, verbose_name='Contract name')
    contractpdf = FileField(null=False, blank=True, storage=InlineEncodedStorage('sponsorcontract'), upload_to=inlineencoded_upload_path, verbose_name='Contract PDF')

    def __unicode__(self):
        return self.contractname

    def clean(self):
        if self.contractpdf and not self.pk:
            raise ValidationError("Can't upload a file until saved at least once! Try again without uploading a file!")

    def save(self, force_insert=False, force_update=False, update_fields=None):
        if not self.contractpdf:
            self.contractpdf.storage._delete(self.id)
        return super(SponsorshipContract, self).save(update_fields=update_fields)
    def delete_inline_storage(self):
        self.contractpdf.storage._delete(self.id)
pre_delete.connect(delete_inline_storage, sender=SponsorshipContract)

class SponsorshipLevel(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    levelname = models.CharField(max_length=100, null=False, blank=False)
    urlname = models.CharField(max_length=100, null=False, blank=False, validators=[validate_lowercase, ])
    levelcost = models.IntegerField(null=False, blank=False, verbose_name="Cost")
    available = models.BooleanField(null=False, blank=False, default=True, verbose_name="Available for signup")
    maxnumber = models.IntegerField(null=False, blank=False, default=0, verbose_name="Maximum number of sponsors")
    instantbuy = models.BooleanField(null=False, blank=False, default=False, verbose_name="Instant buy available")
    paymentmethods = models.ManyToManyField(InvoicePaymentMethod, blank=False, verbose_name="Payment methods for generated invoices")
    contract = models.ForeignKey(SponsorshipContract, blank=True, null=True, on_delete=models.CASCADE)
    canbuyvoucher = models.BooleanField(null=False, blank=False, default=True, verbose_name="Can buy vouchers")
    canbuydiscountcode = models.BooleanField(null=False, blank=False, default=True, verbose_name="Can buy discount codes")

    def __unicode__(self):
        return self.levelname

    class Meta:
        ordering = ('levelcost', 'levelname',)
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
    benefitname = models.CharField(max_length=100, null=False, blank=False)
    sortkey = models.PositiveIntegerField(null=False, blank=False, default=100)
    benefitdescription = models.TextField(null=False, blank=True)
    claimprompt = models.TextField(null=False, blank=True)
    benefit_class = models.IntegerField(null=True, blank=True, default=None, choices=benefit_choices)
    class_parameters = JSONField(blank=True, null=False)
    tweet_template = models.TextField(null=False, blank=True)

    def __unicode__(self):
        return self.benefitname

    class Meta:
        ordering = ('sortkey', 'benefitname', )

class Sponsor(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False, blank=False)
    displayname = models.CharField(max_length=100, null=False, blank=False)
    invoiceaddr = models.TextField(max_length=500, null=False, blank=True)
    vatstatus = models.IntegerField(null=True, blank=False, choices=vat_status_choices)
    vatnumber = models.CharField(max_length=100, null=True, blank=True)
    managers = models.ManyToManyField(User, blank=False)
    url = models.URLField(max_length=200, null=False, blank=True)
    twittername = models.CharField(max_length=100, null=False, blank=True)
    level = models.ForeignKey(SponsorshipLevel, null=False, blank=False, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE)
    confirmed = models.BooleanField(null=False, blank=False, default=False)
    confirmedat = models.DateTimeField(null=True, blank=True)
    confirmedby = models.CharField(max_length=50, null=False, blank=True)
    signupat = models.DateTimeField(null=False, blank=False)

    def __unicode__(self):
        return self.name

class SponsorClaimedBenefit(models.Model):
    sponsor = models.ForeignKey(Sponsor, null=False, blank=False, on_delete=models.CASCADE)
    benefit = models.ForeignKey(SponsorshipBenefit, null=False, blank=False, on_delete=models.CASCADE)
    claimedat = models.DateTimeField(null=False, blank=False)
    claimedby = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    declined = models.BooleanField(null=False, blank=False, default=False)
    claimdata = models.TextField(max_length=500, blank=True, null=False)
    confirmed = models.BooleanField(null=False, blank=False, default=False)

    class Meta:
        unique_together = (('sponsor', 'benefit'),)

class SponsorMail(models.Model):
    conference = models.ForeignKey(Conference, null=False, blank=False, on_delete=models.CASCADE)
    levels = models.ManyToManyField(SponsorshipLevel, blank=False)
    sentat = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    subject = models.CharField(max_length=100, null=False, blank=False)
    message = models.TextField(max_length=8000, null=False, blank=False)

    def __unicode__(self):
        return "%s: %s" % (self.sentat.strftime("%Y-%m-%d %H:%M"), self.subject)

    class Meta:
        ordering = ('-sentat',)

class PurchasedVoucher(models.Model):
    sponsor = models.ForeignKey(Sponsor, null=False, blank=False, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=False, blank=False, on_delete=models.CASCADE)
    regtype = models.ForeignKey(RegistrationType, null=False, blank=False, on_delete=models.CASCADE)
    num = models.IntegerField(null=False, blank=False)
    invoice = models.ForeignKey(Invoice, null=False, blank=False, on_delete=models.CASCADE)
    batch = models.ForeignKey(PrepaidBatch, null=True, blank=True, on_delete=models.CASCADE)
