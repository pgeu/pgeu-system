# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0011_optout'),
    ]

    operations = [
        migrations.RunSQL(
            "UPDATE confreg_conferenceregistration SET regtoken=encode(pgcrypto.digest(pgcrypto.gen_random_bytes(250), 'sha256'), 'hex') WHERE regtoken IS NULL"
        ),
        migrations.AlterField(
            model_name='conferenceregistration',
            name='regtoken',
            field=models.TextField(unique=True),
        ),
        migrations.RunSQL(
            "UPDATE confreg_speaker SET speakertoken=encode(pgcrypto.digest(pgcrypto.gen_random_bytes(250), 'sha256'), 'hex') WHERE speakertoken IS NULL"
        ),
        migrations.AlterField(
            model_name='speaker',
            name='speakertoken',
            field=models.TextField(unique=True),
        ),
    ]
