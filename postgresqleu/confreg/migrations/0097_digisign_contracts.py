# Generated by Django 3.2.14 on 2023-05-14 18:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('digisign', '0001_initial'),
        ('confreg', '0096_recording_consent'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='contractprovider',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='digisign.digisignprovider', verbose_name='Signing provider'),
        ),
        migrations.AddField(
            model_name='conference',
            name='manualcontracts',
            field=models.BooleanField(default=True, help_text='Allow manually signed sponsorship contracts', verbose_name='Manual contracts'),
        ),
        migrations.AddField(
            model_name='conference',
            name='autocontracts',
            field=models.BooleanField(default=True, help_text='Default to automatically approving sponsorships when digital signature process completes', verbose_name='Automated contract workflow'),
        ),
        migrations.AddField(
            model_name='conference',
            name='contractsendername',
            field=models.CharField(max_length=200, null=False, blank=True, help_text='Name used to send digital contracts for this conference', verbose_name='Contract sender name'),
        ),
        migrations.AddField(
            model_name='conference',
            name='contractsenderemail',
            field=models.EmailField(max_length=200, null=False, blank=True, help_text='E-mail address used to send digital contracts for this conference', verbose_name='Contract sender email'),
        ),
        migrations.AddField(
            model_name='conference',
            name='contractexpires',
            field=models.IntegerField(null=False, blank=False, default=7, help_text='Digital contracts will expire after this many days', verbose_name='Contract expiry time'),
        ),
    ]
