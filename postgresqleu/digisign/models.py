from django.db import models

import json


class DigisignProvider(models.Model):
    name = models.CharField(max_length=100, null=False, blank=False, unique=True)
    displayname = models.CharField(max_length=100, null=False, blank=False)
    classname = models.CharField(max_length=200, null=False, blank=False, verbose_name="Implementation class")
    active = models.BooleanField(null=False, blank=False, default=False)
    config = models.JSONField(blank=False, null=False, default=dict)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )

    def get_implementation(self):
        pieces = self.classname.split('.')
        modname = '.'.join(pieces[:-1])
        classname = pieces[-1]
        mod = __import__(modname, fromlist=[classname, ])
        return getattr(mod, classname)(self.id, self)


class DigisignDocument(models.Model):
    provider = models.ForeignKey(DigisignProvider, null=False, blank=False, on_delete=models.CASCADE)
    documentid = models.CharField(max_length=100, null=False, blank=True)
    handler = models.CharField(max_length=32, null=False, blank=True)
    completed = models.BooleanField(null=False, blank=False, default=False)

    class Meta:
        unique_together = (
            ('documentid', 'provider'),
        )


class DigisignLog(models.Model):
    provider = models.ForeignKey(DigisignProvider, null=False, blank=False, on_delete=models.CASCADE)
    document = models.ForeignKey(DigisignDocument, null=True, blank=True, on_delete=models.CASCADE)
    time = models.DateTimeField(auto_now_add=True, db_index=True)
    event = models.CharField(max_length=200, null=False, blank=False)
    text = models.CharField(max_length=1000, null=False, blank=False)
    fulldata = models.JSONField(null=False, blank=False, default=dict)

    class Meta:
        ordering = ('time', )
        indexes = [
            models.Index(fields=('document', '-time'))
        ]

    @property
    def fulldata_pretty(self):
        return json.dumps(self.fulldata, indent=2)
