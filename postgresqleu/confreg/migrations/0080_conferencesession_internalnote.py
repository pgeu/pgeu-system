# Generated by Django 3.2.11 on 2022-02-05 18:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0079_conference_jinjaenabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='conferencesession',
            name='internalnote',
            field=models.TextField(blank=True, verbose_name='Internal notes'),
        ),
    ]
