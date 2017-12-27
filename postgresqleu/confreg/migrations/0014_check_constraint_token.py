# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0013_series_required'),
    ]

    operations = [
		migrations.RunSQL("ALTER TABLE confreg_conferenceregistration ADD CONSTRAINT chk_token_length CHECK (length(regtoken)=64)"),
		migrations.RunSQL("ALTER TABLE confreg_speaker ADD CONSTRAINT chk_token_length CHECK (length(speakertoken)=64)"),
    ]
