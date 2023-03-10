# Generated by Django 3.2.18 on 2023-03-10 11:01

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('confreg', '0095_tweet_conf_time_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConferenceSessionQuestion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.TextField()),
                ('createdat', models.DateTimeField(auto_now_add=True)),
                ('attendee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('conference_session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.conferencesession')),
            ],
            options={
                'ordering': ['-createdat'],
            },
        ),
        migrations.CreateModel(
            name='ConferenceSessionAnswer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answer', models.TextField()),
                ('createdat', models.DateTimeField(auto_now_add=True)),
                ('question', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='session_answer', to='confreg.conferencesessionquestion')),
                ('speaker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='session_answer', to='confreg.speaker')),
            ],
            options={
                'ordering': ['-createdat'],
            },
        ),
    ]
