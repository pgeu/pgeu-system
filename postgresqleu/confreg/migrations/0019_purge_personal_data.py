# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0018_constraint_reg_payments'),
    ]

    operations = [
        migrations.CreateModel(
            name='AggregatedDietary',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('dietary', models.CharField(max_length=100)),
                ('num', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='AggregatedTshirtSizes',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('num', models.IntegerField()),
            ],
        ),
        migrations.AddField(
            model_name='conference',
            name='personal_data_purged',
            field=models.DateTimeField(help_text=b'Personal data for registrations for this conference have been purged', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='aggregatedtshirtsizes',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='aggregatedtshirtsizes',
            name='size',
            field=models.ForeignKey(to='confreg.ShirtSize', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='aggregateddietary',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AlterUniqueTogether(
            name='aggregatedtshirtsizes',
            unique_together=set([('conference', 'size')]),
        ),
        migrations.AlterUniqueTogether(
            name='aggregateddietary',
            unique_together=set([('conference', 'dietary')]),
        ),
    ]
