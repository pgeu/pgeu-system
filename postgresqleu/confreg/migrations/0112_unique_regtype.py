# Generated by Django 3.2.14 on 2024-01-21 13:55

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0111_hashtags_auto'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='registrationtype',
            unique_together={('conference', 'regtype')},
        ),
    ]
