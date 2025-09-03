# Some very simple models used by utilities
from django.db import models


class Storage(models.Model):
    key = models.CharField(max_length=16, null=False, blank=False)
    storageid = models.IntegerField(null=False, blank=False)
    data = models.BinaryField(null=False, blank=False)
    hashval = models.BinaryField(null=False, blank=False)
    metadata = models.JSONField(null=False, blank=False, default=dict)

    class Meta:
        unique_together = (
            ('key', 'storageid'),
        )


class OAuthApplication(models.Model):
    name = models.CharField(max_length=100, null=False, blank=False)
    baseurl = models.URLField(max_length=100, null=False, blank=False, unique=True, verbose_name='Base URL')
    client = models.CharField(max_length=200, null=False, blank=False)
    secret = models.CharField(max_length=200, null=False, blank=False)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'OAuth Application'
