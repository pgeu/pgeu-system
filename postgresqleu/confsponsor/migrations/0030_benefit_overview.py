# Generated by Django 3.2.14 on 2024-04-08 15:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0029_benefit_multiclaim'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsorshipbenefit',
            name='overview_name',
            field=models.CharField(blank=True, max_length=100, verbose_name='Name in overview'),
        ),
        migrations.AddField(
            model_name='sponsorshipbenefit',
            name='overview_value',
            field=models.CharField(blank=True, help_text='Specify this to use a direct value instead of the max claims number as the value', max_length=50, verbose_name='Value in overview'),
        ),
    ]
