# Generated by Django 3.2.11 on 2022-06-20 15:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('elections', '0003_lowercase_email'),
    ]

    operations = [
        migrations.RenameField(
            model_name='election',
            old_name='isopen',
            new_name='isactive',
        ),
        migrations.AlterField(
            model_name='election',
            name='isactive',
            field=models.BooleanField(default=False, verbose_name='Election active'),
        ),
    ]
