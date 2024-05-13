# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('countries', '0001_initial'),
        ('invoices', '0001_initial'),
        ('confreg', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='prepaidbatch',
            name='sponsor',
            field=models.ForeignKey(verbose_name='Optional sponsor', blank=True, to='confsponsor.Sponsor', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='pendingadditionalorder',
            name='invoice',
            field=models.ForeignKey(blank=True, to='invoices.Invoice', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='pendingadditionalorder',
            name='newregtype',
            field=models.ForeignKey(blank=True, to='confreg.RegistrationType', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='pendingadditionalorder',
            name='options',
            field=models.ManyToManyField(to='confreg.ConferenceAdditionalOption'),
        ),
        migrations.AddField(
            model_name='pendingadditionalorder',
            name='reg',
            field=models.ForeignKey(to='confreg.ConferenceRegistration', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='discountcode',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='discountcode',
            name='registrations',
            field=models.ManyToManyField(to='confreg.ConferenceRegistration', blank=True),
        ),
        migrations.AddField(
            model_name='discountcode',
            name='requiresoption',
            field=models.ManyToManyField(help_text='Requires this option to be set in order to be valid', to='confreg.ConferenceAdditionalOption', blank=True, verbose_name="Requires option"),
        ),
        migrations.AddField(
            model_name='discountcode',
            name='requiresregtype',
            field=models.ManyToManyField(help_text='Rrequire a specific registration type to be valid', to='confreg.RegistrationType', blank=True),
        ),
        migrations.AddField(
            model_name='discountcode',
            name='sponsor',
            field=models.ForeignKey(blank=True, to='confsponsor.Sponsor', help_text='Note that if a sponsor is picked, an invoice will be generated once the discount code closes!!!', null=True, verbose_name='Optional sponsor.', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='discountcode',
            name='sponsor_rep',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, help_text='Must be set if the sponsor field is set!', null=True, verbose_name='Optional sponsor representative.', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesessionvote',
            name='session',
            field=models.ForeignKey(to='confreg.ConferenceSession', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesessionvote',
            name='voter',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesessionscheduleslot',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesessionfeedback',
            name='attendee',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesessionfeedback',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesessionfeedback',
            name='session',
            field=models.ForeignKey(to='confreg.ConferenceSession', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='room',
            field=models.ForeignKey(blank=True, to='confreg.Room', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='speaker',
            field=models.ManyToManyField(to='confreg.Speaker', blank=True, verbose_name="Speakers"),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='tentativeroom',
            field=models.ForeignKey(related_name='tentativeroom', blank=True, to='confreg.Room', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='tentativescheduleslot',
            field=models.ForeignKey(blank=True, to='confreg.ConferenceSessionScheduleSlot', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencesession',
            name='track',
            field=models.ForeignKey(blank=True, to='confreg.Track', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='additionaloptions',
            field=models.ManyToManyField(to='confreg.ConferenceAdditionalOption', verbose_name='Additional options', blank=True),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='attendee',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='bulkpayment',
            field=models.ForeignKey(blank=True, to='confreg.BulkPayment', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='country',
            field=models.ForeignKey(verbose_name='Country', to='countries.Country', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='invoice',
            field=models.ForeignKey(blank=True, to='invoices.Invoice', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='regtype',
            field=models.ForeignKey(verbose_name='Registration type', blank=True, to='confreg.RegistrationType', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='shirtsize',
            field=models.ForeignKey(verbose_name='Preferred T-shirt size', blank=True, to='confreg.ShirtSize', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencefeedbackquestion',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencefeedbackanswer',
            name='attendee',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencefeedbackanswer',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferencefeedbackanswer',
            name='question',
            field=models.ForeignKey(to='confreg.ConferenceFeedbackQuestion', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceadditionaloption',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='conferenceadditionaloption',
            name='mutually_exclusive',
            field=models.ManyToManyField(help_text='Mutually exlusive with these additional options', to='confreg.ConferenceAdditionalOption', blank=True),
        ),
        migrations.AddField(
            model_name='conferenceadditionaloption',
            name='requires_regtype',
            field=models.ManyToManyField(help_text='Can only be picked with selected registration types', to='confreg.RegistrationType', blank=True, verbose_name="Requires registration type"),
        ),
        migrations.AddField(
            model_name='conference',
            name='administrators',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, blank=True),
        ),
        migrations.AddField(
            model_name='conference',
            name='staff',
            field=models.ManyToManyField(help_text='Users who can register as staff', related_name='staff_set', to=settings.AUTH_USER_MODEL, blank=True),
        ),
        migrations.AddField(
            model_name='conference',
            name='talkvoters',
            field=models.ManyToManyField(related_name='talkvoters_set', to=settings.AUTH_USER_MODEL, blank=True, help_text="Users who can view talks pre-approval, vote on the talks, and leave comments"),
        ),
        migrations.AddField(
            model_name='conference',
            name='testers',
            field=models.ManyToManyField(related_name='testers_set', to=settings.AUTH_USER_MODEL, blank=True, help_text="Users who can bypass the '<function> is open' check and access pages before they're open, in order to test"),
        ),
        migrations.AddField(
            model_name='bulkpayment',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='bulkpayment',
            name='invoice',
            field=models.ForeignKey(blank=True, to='invoices.Invoice', null=True, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='bulkpayment',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='attendeemail',
            name='conference',
            field=models.ForeignKey(to='confreg.Conference', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='attendeemail',
            name='regclasses',
            field=models.ManyToManyField(to='confreg.RegistrationClass', verbose_name="Registration classes"),
        ),
        migrations.AddField(
            model_name='registrationwaitlisthistory',
            name='waitlist',
            field=models.ForeignKey(to='confreg.RegistrationWaitlistEntry', on_delete=models.CASCADE),
        ),
        migrations.AlterUniqueTogether(
            name='discountcode',
            unique_together=set([('conference', 'code')]),
        ),
        migrations.AlterUniqueTogether(
            name='conferencesessionvote',
            unique_together=set([('session', 'voter')]),
        ),
    ]
