# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os

from django.db import migrations, models

PGCRYPTO_SCHEMA=os.getenv("PGCRYPTO_SCHEMA", "pgcrypto")

class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0011_optout'),
    ]

    operations = [
        migrations.RunSQL(
            "UPDATE confreg_conferenceregistration SET regtoken=encode({PGCRYPTO_SCHEMA}.digest({PGCRYPTO_SCHEMA}.gen_random_bytes(250), 'sha256'), 'hex') WHERE regtoken IS NULL".format(PGCRYPTO_SCHEMA = PGCRYPTO_SCHEMA)
        ),
        migrations.AlterField(
            model_name='conferenceregistration',
            name='regtoken',
            field=models.TextField(unique=True),
        ),
        migrations.RunSQL(
            "UPDATE confreg_speaker SET speakertoken=encode({PGCRYPTO_SCHEMA}.digest({PGCRYPTO_SCHEMA}.gen_random_bytes(250), 'sha256'), 'hex') WHERE speakertoken IS NULL".format(PGCRYPTO_SCHEMA = PGCRYPTO_SCHEMA)
        ),
        migrations.AlterField(
            model_name='speaker',
            name='speakertoken',
            field=models.TextField(unique=True),
        ),
    ]
