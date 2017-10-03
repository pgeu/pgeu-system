# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators
import django.contrib.postgres.fields.ranges


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0007_new_specialtype'),
    ]

    operations = [
        migrations.CreateModel(
            name='VolunteerAssignment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('vol_confirmed', models.BooleanField(default=False, verbose_name=b'Confirmed by volunteer')),
                ('org_confirmed', models.BooleanField(default=False, verbose_name=b'Confirmed by organizers')),
            ],
        ),
        migrations.CreateModel(
            name='VolunteerSlot',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timerange', django.contrib.postgres.fields.ranges.DateTimeRangeField()),
                ('title', models.CharField(max_length=50)),
                ('min_staff', models.IntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('max_staff', models.IntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
            ],
        ),
        migrations.AddField(
            model_name='conference',
            name='volunteers',
            field=models.ManyToManyField(help_text=b'Users who volunteer', related_name='volunteers_set', to='confreg.ConferenceRegistration', blank=True),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='regtoken',
            field=models.TextField(unique=True, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='volunteerslot',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference'),
        ),
        migrations.AddField(
            model_name='volunteerassignment',
            name='reg',
            field=models.ForeignKey(to='confreg.ConferenceRegistration'),
        ),
        migrations.AddField(
            model_name='volunteerassignment',
            name='slot',
            field=models.ForeignKey(to='confreg.VolunteerSlot'),
        ),
		migrations.RunSQL(
			"CREATE INDEX confreg_volunteerslot_timerange_idx ON confreg_volunteerslot USING gist(timerange)",
		),
    ]
