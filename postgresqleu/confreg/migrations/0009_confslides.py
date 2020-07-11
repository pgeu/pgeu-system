# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import postgresqleu.util.fields


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0008_volunteers'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConferenceSessionSlides',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('url', models.URLField(blank=True)),
                ('content', postgresqleu.util.fields.PdfBinaryField(null=True, blank=True, verbose_name='Upload PDF', max_length=20000000000)),
                ('session', models.ForeignKey(to='confreg.ConferenceSession', on_delete=models.CASCADE)),
            ],
            options={'ordering': ('session', 'name',)},
        ),
    ]
