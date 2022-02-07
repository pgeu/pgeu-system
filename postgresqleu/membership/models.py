from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.utils import timezone

from postgresqleu.util.fields import LowercaseEmailField
from postgresqleu.util.time import today_global
from postgresqleu.countries.models import Country
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.membership.util import country_validator_choices

from collections import OrderedDict
from datetime import timedelta


class MeetingType:
    IRC = 0
    WEB = 1

    CHOICES = OrderedDict((
        (IRC, "IRC"),
        (WEB, "Web"),
    ))


STATE_CHOICES = OrderedDict((
    (0, 'Pending'),
    (1, 'Started'),
    (2, 'Finished'),
    (3, 'Closed'),
))


class MembershipConfiguration(models.Model):
    id = models.IntegerField(null=False, blank=False, primary_key=True)
    sender_email = LowercaseEmailField(null=False, blank=False,
                                       help_text="Email address to use as sender on outgoing email")
    sender_name = models.CharField(max_length=100, null=False, blank=False,
                                   help_text='Name to use as sender on outgoing email')
    membership_years = models.IntegerField(null=False, blank=False, default=1,
                                           validators=[MinValueValidator(1), MaxValueValidator(10)],
                                           verbose_name="Membership length",
                                           help_text="Membership length in years")
    membership_cost = models.IntegerField(null=False, blank=False, default=10,
                                          validators=[MinValueValidator(1), ],
                                          verbose_name="Membership cost")
    country_validator = models.CharField(max_length=100, null=False, blank=True,
                                         verbose_name="Country validator",
                                         help_text="Validate member countries against this rule",
                                         choices=country_validator_choices)
    paymentmethods = models.ManyToManyField(InvoicePaymentMethod, blank=False, verbose_name='Invoice payment methods')


def get_config():
    return MembershipConfiguration.objects.get(id=1)


class Member(models.Model):
    user = models.OneToOneField(User, null=False, blank=False, primary_key=True, on_delete=models.CASCADE)
    fullname = models.CharField(max_length=500, null=False, blank=False,
                                verbose_name='Full name')
    country = models.ForeignKey(Country, null=False, blank=False, on_delete=models.CASCADE)
    listed = models.BooleanField(null=False, blank=False, default=True,
                                 verbose_name='Listed in the public membership list')
    paiduntil = models.DateField(null=True, blank=True, verbose_name='Paid until')
    membersince = models.DateField(null=True, blank=True, verbose_name='Member since')

    # If there is a currently active invoice, link to it here so we can
    # easily render the information on the page.
    activeinvoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE)

    # When a membeship expiry warning was last sent, so we don't keep
    # sending them over and over again
    expiry_warning_sent = models.DateTimeField(null=True, blank=True, verbose_name='Expiry warning sent')

    country_exception = models.BooleanField(null=False, blank=False, default=False, help_text="Enable to allow member to bypass country validation")

    # WARNING! New fields should most likely be added to the exclude list
    # in MemberForm!!!

    @property
    def expiressoon(self):
        if self.paiduntil:
            if self.paiduntil < today_global() + timedelta(days=60):
                return True
            else:
                return False
        else:
            return True

    def __str__(self):
        return "%s (%s)" % (self.fullname, self.user.username)


class MemberLog(models.Model):
    member = models.ForeignKey(Member, null=False, blank=False, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(null=False)
    message = models.TextField(null=False, blank=False)

    def __str__(self):
        return "%s: %s" % (self.timestamp, self.message)


class MemberMail(models.Model):
    sentat = models.DateTimeField(null=False, blank=False, auto_now_add=True, db_index=True)
    sentfrom = models.CharField(max_length=100, null=False, blank=False)
    subject = models.CharField(max_length=100, null=False, blank=False)
    message = models.TextField(max_length=8000, null=False, blank=False)
    sentto = models.ManyToManyField(Member, blank=False)


class Meeting(models.Model):
    name = models.CharField(max_length=100, null=False, blank=False)
    dateandtime = models.DateTimeField(null=False, blank=False, verbose_name="Date and time")
    allmembers = models.BooleanField(null=False, blank=False, verbose_name="Open to all members")
    members = models.ManyToManyField(Member, blank=True, verbose_name="Open to specific members")
    meetingtype = models.IntegerField(null=False, blank=False, default=0, choices=MeetingType.CHOICES.items(), verbose_name="Meeting type")
    meetingadmins = models.ManyToManyField(Member, blank=True, related_name='admin_of_meetings', verbose_name="Meeting administrators")
    state = models.IntegerField(null=False, blank=False, default=0, choices=STATE_CHOICES.items())
    botname = models.CharField(max_length=50, null=False, blank=True, verbose_name='Bot name')

    def __str__(self):
        return "%s (%s)" % (self.name, self.dateandtime)

    class Meta:
        ordering = ['-dateandtime', ]

    @property
    def is_open(self):
        # Is this meeting open for joining (doesn't mean it has started!)
        if timezone.now() > self.opentime:
            return True
        return False

    @property
    def opentime(self):
        return self.dateandtime - timedelta(hours=2)

    @property
    def is_started(self):
        return self.state == 1

    @property
    def is_finished(self):
        return self.state == 2

    def get_key_for(self, member):
        try:
            return MemberMeetingKey.objects.get(meeting=self, member=member)
        except MemberMeetingKey.DoesNotExist:
            return None

    @property
    def _display_meetingtype(self):
        return MeetingType.CHOICES.get(self.meetingtype, 'Unknown')

    @property
    def _display_state(self):
        if self.meetingtype == MeetingType.WEB:
            return STATE_CHOICES.get(self.state, 'Unknown')
        else:
            return ''

    def get_all_attendees(self):
        if self.allmembers:
            return Member.objects.filter(paiduntil__gte=self.dateandtime)
        else:
            # Specific members only, but we still require them to be active
            return self.members.filter(paiduntil__gte=self.dateandtime)


class MeetingReminder(models.Model):
    meeting = models.ForeignKey(Meeting, null=False, blank=False, on_delete=models.CASCADE)
    sendat = models.DateTimeField(null=False, blank=False, verbose_name='Send reminder at',
                                  help_text="Reminder will be sent within approximately 15-20 minutes of this timestamp")
    sentat = models.DateTimeField(null=True, blank=True, verbose_name='Reminder sent at')

    class Meta:
        ordering = ('meeting', 'sendat', )
        indexes = [
            models.Index(
                name='idx_membership_reminder_unsent',
                fields=('sendat', ),
                condition=models.Q(sentat__isnull=True)
            ),
        ]


class MemberMeetingKey(models.Model):
    member = models.ForeignKey(Member, null=False, blank=False, on_delete=models.CASCADE)
    meeting = models.ForeignKey(Meeting, null=False, blank=False, on_delete=models.CASCADE)
    key = models.CharField(max_length=100, null=False, blank=False)
    proxyname = models.CharField(max_length=200, null=True, blank=False)
    proxyaccesskey = models.CharField(max_length=100, null=True, blank=False)
    allowrejoin = models.BooleanField(null=False, blank=False, default=False)

    class Meta:
        unique_together = (('member', 'meeting'), )


class MeetingMessageLog(models.Model):
    t = models.DateTimeField(null=False, blank=False)
    meeting = models.ForeignKey(Meeting, null=False, blank=False, on_delete=models.CASCADE)
    sender = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT)
    message = models.TextField()

    class Meta:
        indexes = (
            models.Index(fields=('meeting', 't')),
        )
        ordering = ('meeting', 't', )
