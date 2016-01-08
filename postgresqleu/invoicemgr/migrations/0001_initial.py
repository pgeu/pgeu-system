# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('invoicedate', models.DateTimeField()),
                ('duedate', models.DateField()),
                ('recipient', models.TextField()),
                ('pdf', models.TextField()),
                ('totalamount', models.IntegerField(default=0)),
                ('currency', models.CharField(default=b'\xe2\x82\xac', max_length=3)),
            ],
        ),
    ]
