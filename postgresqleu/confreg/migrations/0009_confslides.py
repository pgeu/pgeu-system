# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


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
                ('content', models.BinaryField(null=True)),
                ('session', models.ForeignKey(to='confreg.ConferenceSession')),
            ],
        ),
    ]
