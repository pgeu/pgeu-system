# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0019_purge_personal_data'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='registrationday',
            unique_together=set([('conference', 'day')]),
        ),
    ]
