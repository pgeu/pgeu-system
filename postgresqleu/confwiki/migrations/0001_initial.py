# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators
import postgresqleu.util.diffablemodel
import postgresqleu.confwiki.models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendeeSignup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('choice', models.CharField(max_length=100, blank=True)),
                ('saved', models.DateTimeField(auto_now=True)),
                ('attendee', models.ForeignKey(to='confreg.ConferenceRegistration')),
            ],
        ),
        migrations.CreateModel(
            name='Signup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=100)),
                ('intro', models.TextField()),
                ('deadline', models.DateTimeField(null=True, blank=True)),
                ('maxsignups', models.IntegerField(default=-1)),
                ('options', models.CharField(blank=True, help_text=b'Comma separated list of options to choose.', max_length=1000, validators=[postgresqleu.confwiki.models.validate_options])),
                ('public', models.BooleanField(default=False, help_text=b'All attendees can sign up')),
                ('visible', models.BooleanField(default=False, help_text=b'Show who have signed up to all invited attendees')),
                ('attendees', models.ManyToManyField(related_name='user_attendees', verbose_name=b'Available to attendees', to='confreg.ConferenceRegistration', blank=True)),
                ('author', models.ForeignKey(to='confreg.ConferenceRegistration')),
                ('conference', models.ForeignKey(to='confreg.Conference')),
                ('regtypes', models.ManyToManyField(related_name='user_regtypes', verbose_name=b'Available to registration types', to='confreg.RegistrationType', blank=True)),
            ],
            options={
                'ordering': ('deadline', 'title'),
            },
        ),
        migrations.CreateModel(
            name='Wikipage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.CharField(max_length=100, validators=[django.core.validators.RegexValidator(regex=b'^[a-zA-Z0-9_-]+$', message=b'Invalid character in urlname. Only alphanumerical, underscore and dash are allowed.')])),
                ('title', models.CharField(max_length=100)),
                ('publishedat', models.DateTimeField(auto_now=True)),
                ('contents', models.TextField()),
                ('publicview', models.BooleanField(default=False, help_text=b'Can all confirmed attendees see this page?', verbose_name=b'Public view')),
                ('publicedit', models.BooleanField(default=False, help_text=b'Can all confirmed attendees edit this page?', verbose_name=b'Public edit')),
                ('history', models.BooleanField(default=True, help_text=b'Can users view the history?')),
                ('author', models.ForeignKey(to='confreg.ConferenceRegistration')),
                ('conference', models.ForeignKey(to='confreg.Conference')),
                ('editor_attendee', models.ManyToManyField(related_name='editor_attendees', verbose_name=b'Editor attendees', to='confreg.ConferenceRegistration', blank=True)),
                ('editor_regtype', models.ManyToManyField(related_name='editor_regtypes', verbose_name=b'Editor registration types', to='confreg.RegistrationType', blank=True)),
                ('viewer_attendee', models.ManyToManyField(related_name='viewer_attendees', verbose_name=b'Viewer attendees', to='confreg.ConferenceRegistration', blank=True)),
                ('viewer_regtype', models.ManyToManyField(related_name='viewer_regtypes', verbose_name=b'Viewer registration types', to='confreg.RegistrationType', blank=True)),
            ],
            options={
                'ordering': ('title',),
            },
            bases=(models.Model, postgresqleu.util.diffablemodel.DiffableModel),
        ),
        migrations.CreateModel(
            name='WikipageHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('publishedat', models.DateTimeField()),
                ('contents', models.TextField()),
                ('author', models.ForeignKey(to='confreg.ConferenceRegistration')),
                ('page', models.ForeignKey(to='confwiki.Wikipage')),
            ],
            options={
                'ordering': ('-publishedat',),
            },
        ),
        migrations.CreateModel(
            name='WikipageSubscriber',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('page', models.ForeignKey(to='confwiki.Wikipage')),
                ('subscriber', models.ForeignKey(to='confreg.ConferenceRegistration')),
            ],
        ),
        migrations.AddField(
            model_name='attendeesignup',
            name='signup',
            field=models.ForeignKey(to='confwiki.Signup'),
        ),
        migrations.AlterUniqueTogether(
            name='wikipagehistory',
            unique_together=set([('page', 'publishedat')]),
        ),
        migrations.AlterUniqueTogether(
            name='wikipage',
            unique_together=set([('conference', 'url')]),
        ),
        migrations.AlterUniqueTogether(
            name='attendeesignup',
            unique_together=set([('signup', 'attendee')]),
        ),
    ]
