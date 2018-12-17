from django.db import models
from django.contrib.auth.models import User


class NewsPosterProfile(models.Model):
    author = models.OneToOneField(User, primary_key=True)
    urlname = models.CharField(max_length=50, null=False, blank=False, unique=True, verbose_name="URL name")
    fullname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Full name")
    canpostglobal = models.BooleanField(null=False, default=False, verbose_name="Can post global news")

    def __unicode__(self):
        return u"{0} ({1})".format(self.fullname, self.urlname)


class News(models.Model):
    title = models.CharField(max_length=128, blank=False)
    datetime = models.DateTimeField(blank=False)
    summary = models.TextField(blank=False)
    author = models.ForeignKey(NewsPosterProfile, null=True)
    highpriorityuntil = models.DateTimeField(null=True, blank=True, verbose_name="High priority until")
    inrss = models.BooleanField(null=False, default=True, verbose_name="Include in RSS feed")
    inarchive = models.BooleanField(null=False, default=True, verbose_name="Include in archives")
    tweeted = models.BooleanField(null=False, blank=False, default=False)

    def __unicode__(self):
        return self.title

    @property
    def pretty_date(self):
        return self.datetime.strftime("%d %B %Y")

    class Meta:
        ordering = ['-datetime', 'title', ]
        verbose_name_plural = 'News'
