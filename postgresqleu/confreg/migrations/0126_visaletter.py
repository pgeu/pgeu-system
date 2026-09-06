# Generated for the visa letter feature.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('confreg', '0125_index_conference_enddate'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='visa_letter_enabled',
            field=models.BooleanField(default=False, help_text='Allow eligible attendees to request a visa invitation letter', verbose_name='Visa letters'),
        ),
        migrations.AddField(
            model_name='conference',
            name='visa_letter_city',
            field=models.CharField(blank=True, help_text='City the conference is held in, as it should appear in the visa letter (e.g. "Berlin")', max_length=100, verbose_name='Visa letter city'),
        ),
        migrations.AddField(
            model_name='conference',
            name='visa_letter_country',
            field=models.CharField(blank=True, help_text='Country the conference is held in, as it should appear in the visa letter (e.g. "Germany")', max_length=100, verbose_name='Visa letter country'),
        ),
        migrations.AddField(
            model_name='conference',
            name='visa_letter_signer',
            field=models.TextField(blank=True, help_text='Multi-line text printed below the signature image: name, title, address, phone, email', verbose_name='Visa letter signer'),
        ),
        migrations.CreateModel(
            name='VisaLetterRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('pending', 'Pending review'), ('changes_needed', 'Changes needed'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('admin_notes', models.TextField(blank=True, default='', verbose_name='Admin notes')),
                ('accommodation_covered', models.BooleanField(default=False, help_text='Tick if accommodation and travel costs are covered for this attendee; the visa letter will state this.', verbose_name='Accommodation and travel covered')),
                ('passport_name', models.CharField(max_length=200, verbose_name='Full name on passport')),
                ('passport_sex', models.CharField(choices=[('male', 'Male'), ('female', 'Female')], max_length=10, verbose_name='Sex (as on passport)')),
                ('date_of_birth', models.DateField(verbose_name='Date of birth')),
                ('passport_number', models.CharField(max_length=50, verbose_name='Passport number')),
                ('nationality', models.CharField(max_length=100, verbose_name='Nationality')),
                ('home_address', models.TextField(verbose_name='Home address')),
                ('embassy_name', models.CharField(max_length=200, verbose_name='Embassy / consulate name')),
                ('embassy_address', models.TextField(verbose_name='Embassy / consulate address')),
                ('entry_date', models.DateField(verbose_name='Planned entry date')),
                ('exit_date', models.DateField(verbose_name='Planned exit date')),
                ('accommodation', models.CharField(max_length=200, verbose_name='Accommodation while in country')),
                ('contact_info', models.CharField(max_length=200, verbose_name='Contact info while in country')),
                ('conference', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.conference')),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.conferenceregistration')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
                'unique_together': {('conference', 'registration')},
            },
        ),
    ]
