# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import postgresqleu.util.forms


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0022_ask_more_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessToken',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('token', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('permissions', postgresqleu.util.forms.ChoiceArrayField(base_field=models.CharField(max_length=32, choices=[(b'regtypes', b'Registration types and counters'), (b'discounts', b'Discount codes'), (b'vouchers', b'Voucher codes'), (b'sponsors', b'Sponsors and counts')]), size=None)),
                ('conference', models.ForeignKey(to='confreg.Conference')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='accesstoken',
            unique_together=set([('conference', 'token')]),
        ),
    ]
