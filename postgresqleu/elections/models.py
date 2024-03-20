from django.db import models
from postgresqleu.util.fields import LowercaseEmailField
from postgresqleu.membership.models import Member


class Election(models.Model):
    name = models.CharField(max_length=100, null=False, blank=False)
    startdate = models.DateField(null=False, blank=False, verbose_name="Start date")
    enddate = models.DateField(null=False, blank=False, verbose_name="End date")
    slots = models.IntegerField(null=False, default=1)
    isactive = models.BooleanField(null=False, default=False, verbose_name='Election active')
    resultspublic = models.BooleanField(null=False, default=False, verbose_name='Results public')
    intro = models.TextField(null=False, blank=True, verbose_name="Introduction text")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('-startdate', )


class Candidate(models.Model):
    election = models.ForeignKey(Election, null=False, blank=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False, blank=False)
    email = LowercaseEmailField(max_length=200, null=False, blank=False)
    presentation = models.TextField(null=False, blank=False)

    def __str__(self):
        return "%s (%s)" % (self.name, self.election)


class Vote(models.Model):
    election = models.ForeignKey(Election, null=False, blank=False, on_delete=models.CASCADE)
    voter = models.ForeignKey(Member, null=False, blank=False, on_delete=models.CASCADE)
    candidate = models.ForeignKey(Candidate, null=False, blank=False, on_delete=models.CASCADE)
    score = models.IntegerField(null=False, blank=False)
