# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CMutuelTransaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('opdate', models.DateField()),
                ('valdate', models.DateField()),
                ('amount', models.DecimalField(max_digits=10, decimal_places=2)),
                ('description', models.CharField(max_length=300)),
                ('balance', models.DecimalField(max_digits=10, decimal_places=2)),
                ('sent', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('-opdate',),
                'verbose_name': 'CMutuel Transaction',
                'verbose_name_plural': 'CMutuel Transactions',
            },
        ),
    ]
