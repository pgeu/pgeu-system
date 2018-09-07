# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0006_require_contenttypes_0002'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('confreg', '0010_longerurls'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConferenceSeries',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name='ConferenceSeriesOptOut',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('series', models.ForeignKey(to='confreg.ConferenceSeries', on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='GlobalOptOut',
            fields=[
                ('user', models.OneToOneField(primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='speaker',
            name='speakertoken',
            field=models.TextField(unique=True, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='conferenceseriesoptout',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conference',
            name='series',
            field=models.ForeignKey(blank=True, to='confreg.ConferenceSeries', null=True, on_delete=models.CASCADE),
        ),
        migrations.AlterUniqueTogether(
            name='conferenceseriesoptout',
            unique_together=set([('user', 'series')]),
        ),
    ]
