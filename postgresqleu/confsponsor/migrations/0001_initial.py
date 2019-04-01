# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import postgresqleu.util.validators
from django.conf import settings
import postgresqleu.util.storage


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('invoices', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchasedVoucher',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('num', models.IntegerField()),
                ('batch', models.ForeignKey(blank=True, to='confreg.PrepaidBatch', null=True, on_delete=models.CASCADE)),
                ('invoice', models.ForeignKey(to='invoices.Invoice', on_delete=models.CASCADE)),
                ('regtype', models.ForeignKey(to='confreg.RegistrationType', on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='Sponsor',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('invoiceaddr', models.TextField(max_length=500, blank=True)),
                ('twittername', models.CharField(max_length=100, blank=True)),
                ('confirmed', models.BooleanField(default=False)),
                ('confirmedat', models.DateTimeField(null=True, blank=True)),
                ('confirmedby', models.CharField(max_length=50, blank=True)),
                ('conference', models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE)),
                ('invoice', models.ForeignKey(blank=True, to='invoices.Invoice', null=True, on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='SponsorClaimedBenefit',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('claimedat', models.DateTimeField()),
                ('declined', models.BooleanField(default=False)),
                ('claimdata', models.TextField(max_length=500, blank=True)),
                ('confirmed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='SponsorMail',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sentat', models.DateTimeField(auto_now_add=True)),
                ('subject', models.CharField(max_length=100)),
                ('message', models.TextField(max_length=8000)),
                ('conference', models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('-sentat',),
            },
        ),
        migrations.CreateModel(
            name='SponsorshipBenefit',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('benefitname', models.CharField(max_length=100, verbose_name='Benefit name')),
                ('sortkey', models.PositiveIntegerField(default=100, verbose_name='Sort key')),
                ('benefitdescription', models.TextField(blank=True, verbose_name='Benefit description')),
                ('claimprompt', models.TextField(blank=True, verbose_name='Claim prompt')),
                ('benefit_class', models.IntegerField(default=None, null=True, blank=True, choices=[(1, 'Require uploaded image'), (2, 'Requires explicit claiming'), (3, 'Claim entry vouchers'), (4, 'Provide text string'), (5, 'List of attendee email addresses')])),
                ('class_parameters', models.TextField(max_length=500, blank=True, default='{}')),
            ],
            options={
                'ordering': ('sortkey', 'benefitname'),
            },
        ),
        migrations.CreateModel(
            name='SponsorshipContract',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('contractname', models.CharField(max_length=100, verbose_name='Contract name')),
                ('contractpdf', models.FileField(storage=postgresqleu.util.storage.InlineEncodedStorage('sponsorcontract'), upload_to=postgresqleu.util.storage.inlineencoded_upload_path, blank=True, verbose_name='Contract PDF')),
            ],
        ),
        migrations.CreateModel(
            name='SponsorshipLevel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('levelname', models.CharField(max_length=100, verbose_name='Level name')),
                ('urlname', models.CharField(max_length=100, validators=[postgresqleu.util.validators.validate_lowercase], verbose_name='URL name')),
                ('levelcost', models.IntegerField(verbose_name="Cost")),
                ('available', models.BooleanField(default=True, verbose_name='Available for signup')),
                ('instantbuy', models.BooleanField(default=False, verbose_name="Instant buy available")),
                ('canbuyvoucher', models.BooleanField(default=True, verbose_name="Can buy vouchers")),
                ('canbuydiscountcode', models.BooleanField(default=True, verbose_name="Can buy discount codes")),
                ('conference', models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE)),
                ('contract', models.ForeignKey(blank=True, to='confsponsor.SponsorshipContract', null=True, on_delete=models.CASCADE)),
                ('paymentmethods', models.ManyToManyField(to='invoices.InvoicePaymentMethod', verbose_name='Payment methods for generated invoices')),
            ],
            options={
                'ordering': ('levelcost', 'levelname'),
            },
        ),
        migrations.AddField(
            model_name='sponsorshipbenefit',
            name='level',
            field=models.ForeignKey(to='confsponsor.SponsorshipLevel', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='sponsormail',
            name='levels',
            field=models.ManyToManyField(to='confsponsor.SponsorshipLevel', blank=True),
        ),
        migrations.AddField(
            model_name='sponsorclaimedbenefit',
            name='benefit',
            field=models.ForeignKey(to='confsponsor.SponsorshipBenefit', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='sponsorclaimedbenefit',
            name='claimedby',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='sponsorclaimedbenefit',
            name='sponsor',
            field=models.ForeignKey(to='confsponsor.Sponsor', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='sponsor',
            name='level',
            field=models.ForeignKey(to='confsponsor.SponsorshipLevel', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='sponsor',
            name='managers',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='purchasedvoucher',
            name='sponsor',
            field=models.ForeignKey(to='confsponsor.Sponsor', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='purchasedvoucher',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AlterUniqueTogether(
            name='sponsorshiplevel',
            unique_together=set([('conference', 'urlname')]),
        ),
        migrations.AlterUniqueTogether(
            name='sponsorclaimedbenefit',
            unique_together=set([('sponsor', 'benefit')]),
        ),
    ]
