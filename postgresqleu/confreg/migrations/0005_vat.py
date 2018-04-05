# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0005_vat'),
        ('confreg', '0004_timediff'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='vat_registrations',
            field=models.ForeignKey(related_name='vat_registrations', verbose_name=b'VAT rate for registrations', blank=True, to='invoices.VatRate', null=True),
        ),
        migrations.AddField(
            model_name='conference',
            name='vat_sponsorship',
            field=models.ForeignKey(related_name='vat_sponsorship', verbose_name=b'VAT rate for sponsorships', blank=True, to='invoices.VatRate', null=True),
        ),
        migrations.AlterField(
            model_name='conferenceadditionaloption',
            name='cost',
            field=models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Cost excluding VAT."),
        ),
        migrations.AlterField(
            model_name='discountcode',
            name='discountamount',
            field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
        ),
        migrations.AlterField(
            model_name='registrationtype',
            name='cost',
            field=models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Cost excluding VAT."),
        ),
    ]
