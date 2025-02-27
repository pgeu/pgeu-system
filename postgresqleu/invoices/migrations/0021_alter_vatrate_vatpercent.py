# Generated by Django 3.2.22 on 2024-09-29 02:12

import django.core.validators
from django.db import migrations
import postgresqleu.invoices.models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0020_regtransfer_processor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vatrate',
            name='vatpercent',
            field=postgresqleu.util.fields.NormalizedDecimalField(decimal_places=6, default=0, max_digits=9, validators=[django.core.validators.MaxValueValidator(100), django.core.validators.MinValueValidator(0)], verbose_name='VAT percentage'),
        ),
    ]
