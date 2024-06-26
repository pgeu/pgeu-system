# Generated by Django 4.2.11 on 2024-05-14 13:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0030_benefit_overview'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsormail',
            name='sent',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='sponsormail',
            name='sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name='sponsormail',
            index=models.Index(condition=models.Q(('sent', False)), fields=['sentat'], name='confsponsor_sponsormail_unsent'),
        ),
    ]
