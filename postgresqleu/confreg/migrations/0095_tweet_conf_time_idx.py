# Generated by Django 3.2.14 on 2023-01-16 13:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0094_decimal_refund_fees'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='conferencetweetqueue',
            index=models.Index(fields=['conference', '-datetime'], name='confreg_con_confere_e842d8_idx'),
        ),
    ]
