# Generated by Django 3.2.14 on 2023-05-14 17:09

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0021_scannedattendee_firstscan'),
        ('digisign', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsorshipcontract',
            name='fieldjson',
            field=models.JSONField(default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder),
        ),
        migrations.AddField(
            model_name='sponsor',
            name='signmethod',
            field=models.IntegerField(null=False, blank=False, default=1, choices=((0, 'Digital signatures'), (1, 'Manual signatures')), verbose_name='Signing method'),
        ),
        migrations.AddField(
            model_name='sponsor',
            name='contract',
            field=models.OneToOneField(null=True, blank=True, to='digisign.DigisignDocument',
                                       on_delete=models.SET_NULL,
                                       help_text="Contract, when using digital signatures"),
        ),
        migrations.AddField(
            model_name='sponsor',
            name='autoapprovesigned',
            field=models.BooleanField(null=False, blank=False, default=True, verbose_name='Approve on signing',
                                      help_text="Automatically approve once digital signatures are completed"),
        ),
    ]
