# Generated by Django 3.2.14 on 2024-04-07 11:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0027_sponsoradditionalcontract'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsorshipbenefit',
            name='deadline',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Claim deadline'),
        ),
    ]
