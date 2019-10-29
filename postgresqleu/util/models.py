# Some very simple models used by utilities
from django.db import models


class Storage(models.Model):
    key = models.CharField(max_length=16, null=False, blank=False)
    storageid = models.IntegerField(null=False, blank=False)
    data = models.BinaryField(null=False, blank=False)

    class Meta:
        unique_together = (
            ('key', 'storageid'),
        )
