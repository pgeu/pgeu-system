from django.db import models
from django.core.exceptions import ValidationError


def nonzero_validator(value):
    if value == 0:
        raise ValidationError("Must be non-zero value!")


ACCOUNT_OBJECT_CHOICES = (
    (0, "Optional"),
    (1, "Required"),
    (2, "Forbidden"),
)


class AccountClass(models.Model):
    name = models.CharField(max_length=100)
    inbalance = models.BooleanField(null=False, blank=False, default=False, verbose_name='In balance',
                                    help_text='Is this account class listed in the balance report (instead of results report)')
    balancenegative = models.BooleanField(null=False, blank=False, default=False, verbose_name='Balance negative',
                                          help_text='Should the sign of the balance of this account be reversed in the report')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Account class'
        verbose_name_plural = 'Account classes'
        ordering = ('name', )


class AccountGroup(models.Model):
    name = models.CharField(max_length=100)
    accountclass = models.ForeignKey(AccountClass, blank=False, default=False, on_delete=models.CASCADE,
                                     verbose_name='Account class')
    foldable = models.BooleanField(null=False, blank=False, default=False,
                                   help_text='If this account is alone in the group having values, fold it into a single line and rmeove the group header/footer')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )


class Account(models.Model):
    num = models.IntegerField(verbose_name="Account number", unique=True)
    group = models.ForeignKey(AccountGroup, null=False, blank=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    availableforinvoicing = models.BooleanField(null=False, blank=False, default=False,
                                                verbose_name='Available for invoicing',
                                                help_text='List this account in the dropdown when creating a manual invoice')
    objectrequirement = models.IntegerField(null=False, default=0, choices=ACCOUNT_OBJECT_CHOICES,
                                            verbose_name="Object required",
                                            help_text='Require an object to be specified when using this account')

    def __str__(self):
        return "%s - %s" % (self.num, self.name)

    class Meta:
        ordering = ('num', )


class Year(models.Model):
    year = models.IntegerField(primary_key=True)
    isopen = models.BooleanField(null=False, blank=False)

    def __str__(self):
        if self.isopen:
            return "%s *" % self.year
        return "%s" % self.year

    class Meta:
        ordering = ('-year',)


class IncomingBalance(models.Model):
    year = models.ForeignKey(Year, null=False, blank=False, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, to_field='num', null=False, blank=False, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=False, blank=False, validators=[nonzero_validator, ])

    def __str__(self):
        return "%s / %s" % (self.year_id, self.account)

    class Meta:
        ordering = ('year__pk', 'account')
        unique_together = (('year', 'account'),)


class Object(models.Model):
    name = models.CharField(max_length=30, null=False, blank=False)
    active = models.BooleanField(null=False, blank=False, default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )


class JournalEntry(models.Model):
    year = models.ForeignKey(Year, null=False, blank=False, on_delete=models.CASCADE)
    seq = models.IntegerField(null=False, blank=False)
    date = models.DateField(null=False, blank=False)
    closed = models.BooleanField(blank=False, null=False, default=False)

    def __str__(self):
        return "%s-%04d (%s)" % (self.year.year, self.seq, self.date)

    class Meta:
        unique_together = (('year', 'seq'), )


class JournalItem(models.Model):
    journal = models.ForeignKey(JournalEntry, null=False, blank=False, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, to_field='num', null=False, blank=False, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=False, blank=False, validators=[nonzero_validator, ])
    object = models.ForeignKey(Object, null=True, blank=True, on_delete=models.CASCADE)
    description = models.CharField(max_length=200, null=False, blank=False)

    @property
    def debit(self):
        if self.amount > 0:
            return self.amount
        return ""

    @property
    def credit(self):
        if self.amount < 0:
            return -self.amount
        return ""


class JournalUrl(models.Model):
    journal = models.ForeignKey(JournalEntry, null=False, blank=False, on_delete=models.CASCADE)
    url = models.URLField(null=False, blank=False)

    def __str__(self):
        return self.url
