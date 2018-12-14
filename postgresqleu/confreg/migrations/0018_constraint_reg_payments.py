# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0017_payconfirmedat_timestamp'),
    ]

    operations = [
        migrations.RunSQL("ALTER TABLE confreg_conferenceregistration ADD CONSTRAINT chk_payment_ids CHECK (NOT (invoice_id IS NOT NULL AND bulkpayment_id IS NOT NULL))"),
    ]
