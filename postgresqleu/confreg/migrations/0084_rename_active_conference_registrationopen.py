# Generated by Django 3.2.11 on 2022-06-25 17:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0083_calls_timerange'),
    ]

    operations = [
        migrations.RenameField(
            model_name='conference',
            old_name='active',
            new_name='registrationopen',
        ),
    ]
