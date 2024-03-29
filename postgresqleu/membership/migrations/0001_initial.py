# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0006_require_contenttypes_0002'),
        ('countries', '0001_initial'),
        ('invoices', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Meeting',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('dateandtime', models.DateTimeField(verbose_name='Date and time')),
                ('allmembers', models.BooleanField(verbose_name='Open to all members')),
                ('botname', models.CharField(max_length=50)),
            ],
            options={
                'ordering': ['-dateandtime', ],
            }
        ),
        migrations.CreateModel(
            name='Member',
            fields=[
                ('user', models.OneToOneField(primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('fullname', models.CharField(max_length=500, verbose_name='Full name')),
                ('listed', models.BooleanField(default=True, verbose_name='Listed in the public membership list')),
                ('paiduntil', models.DateField(null=True, blank=True, verbose_name='Paid until')),
                ('membersince', models.DateField(null=True, blank=True, verbose_name='Member since')),
                ('expiry_warning_sent', models.DateTimeField(null=True, blank=True, verbose_name='Expiry warning sent')),
                ('activeinvoice', models.ForeignKey(blank=True, to='invoices.Invoice', null=True, on_delete=models.CASCADE)),
                ('country', models.ForeignKey(to='countries.Country', on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='MemberLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField()),
                ('message', models.TextField()),
                ('member', models.ForeignKey(to='membership.Member', on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='MemberMeetingKey',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('key', models.CharField(max_length=100)),
                ('meeting', models.ForeignKey(to='membership.Meeting', on_delete=models.CASCADE)),
                ('member', models.ForeignKey(to='membership.Member', on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='meeting',
            name='members',
            field=models.ManyToManyField(to='membership.Member', blank=True, verbose_name='Open to specific members'),
        ),
        migrations.AlterUniqueTogether(
            name='membermeetingkey',
            unique_together=set([('member', 'meeting')]),
        ),
    ]
