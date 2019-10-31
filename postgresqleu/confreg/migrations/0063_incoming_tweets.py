# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-10-10 22:18
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('confreg', '0062_tweet_approval'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConferenceIncomingTweet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('statusid', models.BigIntegerField(unique=True)),
                ('created', models.DateTimeField()),
                ('processedat', models.DateTimeField(blank=True, null=True)),
                ('text', models.CharField(max_length=512)),
                ('replyto_statusid', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('author_id', models.BigIntegerField()),
                ('author_screenname', models.CharField(max_length=50)),
                ('author_name', models.CharField(max_length=100)),
                ('author_image_url', models.URLField(max_length=1024)),
                ('quoted_statusid', models.BigIntegerField(blank=True, null=True)),
                ('quoted_text', models.CharField(blank=True, max_length=512, null=True)),
                ('quoted_permalink', models.URLField(blank=True, max_length=1024, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='conference',
            name='twitterincoming_active',
            field=models.BooleanField(default=False, verbose_name='Twitter incoming polling active'),
        ),
        migrations.AddField(
            model_name='conferencetweetqueue',
            name='replytotweetid',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='Reply to tweet'),
        ),
        migrations.AddField(
            model_name='conferencetweetqueue',
            name='tweetid',
            field=models.BigIntegerField(db_index=True, default=0),
        ),
        migrations.AddField(
            model_name='conferenceincomingtweet',
            name='conference',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.Conference'),
        ),
        migrations.AddField(
            model_name='conferenceincomingtweet',
            name='processedby',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
    ]