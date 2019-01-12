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
                ('attendee', models.ForeignKey(to='confreg.ConferenceRegistration', on_delete=models.CASCADE)),
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
                ('options', models.CharField(blank=True, help_text='Comma separated list of options to choose.', max_length=1000, validators=[postgresqleu.confwiki.models.validate_options])),
                ('public', models.BooleanField(default=False, help_text='All attendees can sign up')),
                ('visible', models.BooleanField(default=False, help_text='Show who have signed up to all invited attendees')),
                ('attendees', models.ManyToManyField(related_name='user_attendees', verbose_name='Available to attendees', to='confreg.ConferenceRegistration', blank=True)),
                ('author', models.ForeignKey(to='confreg.ConferenceRegistration', on_delete=models.CASCADE)),
                ('conference', models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE)),
                ('regtypes', models.ManyToManyField(related_name='user_regtypes', verbose_name='Available to registration types', to='confreg.RegistrationType', blank=True)),
            ],
            options={
                'ordering': ('deadline', 'title'),
            },
        ),
        migrations.CreateModel(
            name='Wikipage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.CharField(max_length=100, validators=[django.core.validators.RegexValidator(regex='^[a-zA-Z0-9_-]+$', message='Invalid character in urlname. Only alphanumerical, underscore and dash are allowed.')])),
                ('title', models.CharField(max_length=100)),
                ('publishedat', models.DateTimeField(auto_now=True)),
                ('contents', models.TextField()),
                ('publicview', models.BooleanField(default=False, help_text='Can all confirmed attendees see this page?', verbose_name='Public view')),
                ('publicedit', models.BooleanField(default=False, help_text='Can all confirmed attendees edit this page?', verbose_name='Public edit')),
                ('history', models.BooleanField(default=True, help_text='Can users view the history?')),
                ('author', models.ForeignKey(to='confreg.ConferenceRegistration', on_delete=models.CASCADE)),
                ('conference', models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE)),
                ('editor_attendee', models.ManyToManyField(related_name='editor_attendees', verbose_name='Editor attendees', to='confreg.ConferenceRegistration', blank=True)),
                ('editor_regtype', models.ManyToManyField(related_name='editor_regtypes', verbose_name='Editor registration types', to='confreg.RegistrationType', blank=True)),
                ('viewer_attendee', models.ManyToManyField(related_name='viewer_attendees', verbose_name='Viewer attendees', to='confreg.ConferenceRegistration', blank=True)),
                ('viewer_regtype', models.ManyToManyField(related_name='viewer_regtypes', verbose_name='Viewer registration types', to='confreg.RegistrationType', blank=True)),
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
                ('author', models.ForeignKey(to='confreg.ConferenceRegistration', on_delete=models.CASCADE)),
                ('page', models.ForeignKey(to='confwiki.Wikipage', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('-publishedat',),
            },
        ),
        migrations.CreateModel(
            name='WikipageSubscriber',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('page', models.ForeignKey(to='confwiki.Wikipage', on_delete=models.CASCADE)),
                ('subscriber', models.ForeignKey(to='confreg.ConferenceRegistration', on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='attendeesignup',
            name='signup',
            field=models.ForeignKey(to='confwiki.Signup', on_delete=models.CASCADE),
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
