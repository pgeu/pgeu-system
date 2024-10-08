# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-12-25 22:23
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0038_attendee_reg_email'),
    ]

    operations = [
        migrations.RunSQL("SET CONSTRAINTS ALL IMMEDIATE"),
        migrations.AddField(
            model_name='conference',
            name='checkinactive',
            field=models.BooleanField(default=False, verbose_name='Check-in active'),
        ),
        migrations.AddField(
            model_name='conference',
            name='checkinprocessors',
            field=models.ManyToManyField(blank=True, help_text='Users who process checkins', related_name='checkinprocessors_set', to='confreg.ConferenceRegistration', verbose_name='Check-in processors'),
        ),
        migrations.AddField(
            model_name='conference',
            name='queuepartitioning',
            field=models.IntegerField(blank=True, choices=[(1, 'By last name'), (2, 'By first name')], help_text='If queue partitioning is used, partition by what?', null=True, verbose_name='Queue partitioning'),
        ),
        migrations.AddField(
            model_name='conference',
            name='tickets',
            field=models.BooleanField(default=False, help_text='Generate and send tickets to all attendees once their registration is completed.', verbose_name='Use tickets'),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='checkedinat',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Checked in at'),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='checkedinby',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='confreg.ConferenceRegistration', verbose_name='Checked by by'),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='idtoken',
            field=models.TextField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='publictoken',
            field=models.TextField(blank=True, null=True, unique=True),
        ),
        migrations.RunSQL(
            """WITH t AS (
  SELECT r.id, string_agg(lpad(to_hex((random() * 255)::int)::text, 2, '0'),'') AS rnd
  FROM confreg_conferenceregistration r CROSS JOIN generate_series(1,32) g(g)
  WHERE r.idtoken IS NULL GROUP BY r.id
)
UPDATE confreg_conferenceregistration rr SET idtoken=rnd FROM t WHERE t.id=rr.id""",
        ),
        migrations.RunSQL(
            """WITH t AS (
  SELECT r.id, string_agg(lpad(to_hex((random() * 255)::int)::text, 2, '0'),'') AS rnd
  FROM confreg_conferenceregistration r CROSS JOIN generate_series(1,32) g(g)
  WHERE r.publictoken IS NULL GROUP BY r.id
)
UPDATE confreg_conferenceregistration rr SET publictoken=rnd FROM t WHERE t.id=rr.id""",
        ),
        migrations.AlterField(
            model_name='conferenceregistration',
            name='idtoken',
            field=models.TextField(unique=True),
        ),
        migrations.AlterField(
            model_name='conferenceregistration',
            name='publictoken',
            field=models.TextField(unique=True),
        ),
    ]
