# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0025_edit_registrations'),
        ('confsponsor', '0006_track_sponsor_signup_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsorshipcontract',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', null=True),
        ),
        migrations.RunSQL("UPDATE confsponsor_sponsorshipcontract c SET conference_id=(SELECT conference_id FROM confsponsor_sponsorshiplevel l WHERE l.contract_id=c.id LIMIT 1)"),
        migrations.AlterField(
            model_name='sponsorshipcontract',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', null=False),
        ),
    ]
