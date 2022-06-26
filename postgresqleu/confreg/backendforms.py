from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.db.models.expressions import F
from django.contrib import messages
import django.forms
import django.forms.widgets
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.conf import settings

import datetime
from collections import OrderedDict
from urllib.parse import urlparse
from psycopg2.extras import DateTimeTZRange
import pytz

from postgresqleu.util.db import exec_to_single_list, exec_to_scalar
from postgresqleu.util.crypto import generate_rsa_keypair
from postgresqleu.util.forms import SelectSetValueField
from postgresqleu.util.widgets import StaticTextWidget, EmailTextWidget, MonospaceTextarea
from postgresqleu.util.widgets import TagOptionsTextWidget
from postgresqleu.util.random import generate_random_token
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.util.messaging import messaging_implementation_choices, get_messaging, get_messaging_class
from postgresqleu.util.messaging.util import get_shortened_post_length

import postgresqleu.accounting.models

from postgresqleu.confreg.models import Conference, ConferenceRegistration, ConferenceAdditionalOption
from postgresqleu.confreg.models import RegistrationClass, RegistrationType, RegistrationDay
from postgresqleu.confreg.models import ConferenceFeedbackQuestion, Speaker
from postgresqleu.confreg.models import ConferenceSession, Track, Room, ConferenceSessionTag
from postgresqleu.confreg.models import ConferenceSessionSlides
from postgresqleu.confreg.models import ConferenceSessionScheduleSlot, VolunteerSlot
from postgresqleu.confreg.models import DiscountCode, AccessToken, AccessTokenPermissions
from postgresqleu.confreg.models import ConferenceSeries
from postgresqleu.confreg.models import ConferenceNews
from postgresqleu.confreg.models import ConferenceTweetQueue, ConferenceHashtag
from postgresqleu.confreg.models import ShirtSize
from postgresqleu.confreg.models import RefundPattern
from postgresqleu.confreg.models import ConferenceMessaging
from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.newsevents.models import NewsPosterProfile

from postgresqleu.confreg.models import valid_status_transitions, get_status_string
from postgresqleu.confreg.models import STATUS_CHOICES

from postgresqleu.util.backendlookups import GeneralAccountLookup, CountryLookup
from postgresqleu.confreg.backendlookups import RegisteredUsersLookup, SpeakerLookup, SessionTagLookup

from postgresqleu.confreg.campaigns import allcampaigns
from postgresqleu.confreg.regtypes import validate_special_reg_type_setup


class BackendConferenceForm(BackendForm):
    helplink = 'configuring#conferenceform'
    markdown_fields = ['promotext', ]
    selectize_multiple_fields = {
        'testers': GeneralAccountLookup(),
        'talkvoters': GeneralAccountLookup(),
        'staff': GeneralAccountLookup(),
        'volunteers': RegisteredUsersLookup(None),
        'checkinprocessors': RegisteredUsersLookup(None),
        'initial_common_countries': CountryLookup(),
    }

    class Meta:
        model = Conference
        fields = ['registrationopen', 'registrationtimerange', 'callforpapersopen', 'callforpaperstimerange',
                  'callforsponsorsopen', 'callforsponsorstimerange', 'feedbackopen', 'checkinactive',
                  'conferencefeedbackopen', 'scheduleactive', 'sessionsactive', 'cardsactive', 'allowedit',
                  'promoactive', 'promotext', 'promopicurl',
                  'twitter_timewindow_start', 'twitter_timewindow_end', 'twitter_postpolicy',
                  'schedulewidth', 'pixelsperminute', 'notifyregs', 'notifysessionstatus', 'notifyvolunteerstatus',
                  'testers', 'talkvoters', 'staff', 'volunteers', 'checkinprocessors',
                  'asktshirt', 'askfood', 'asknick', 'asktwitter', 'askbadgescan', 'askshareemail', 'askphotoconsent',
                  'skill_levels', 'additionalintro', 'callforpapersintro', 'showvotes', 'callforpaperstags', 'sendwelcomemail', 'welcomemail',
                  'tickets', 'queuepartitioning', 'invoice_autocancel_hours', 'attendees_before_waitlist',
                  'initial_common_countries', 'jinjaenabled']
        widgets = {
            'welcomemail': EmailTextWidget,
        }

    def fix_fields(self):
        self.selectize_multiple_fields['volunteers'] = RegisteredUsersLookup(self.conference)
        self.selectize_multiple_fields['checkinprocessors'] = RegisteredUsersLookup(self.conference)
        self.fields['notifyregs'].help_text = 'Notifications will be sent to {} whenever someone registers or cancels.'.format(self.conference.notifyaddr)
        self.fields['notifysessionstatus'].help_text = 'Notifications will be sent to {} whenever a speaker confirms a session.'.format(self.conference.notifyaddr)
        self.fields['notifyvolunteerstatus'].help_text = 'Notifications will be sent to {} whenever a volunteer makes changes to a slot.'.format(self.conference.notifyaddr)

    fieldsets = [
        {'id': 'base_info', 'legend': 'Basic information', 'fields': ['attendees_before_waitlist', 'invoice_autocancel_hours', 'notifyregs', 'notifysessionstatus', 'notifyvolunteerstatus', ]},
        {'id': 'welcomeandreg', 'legend': 'Welcome and registration', 'fields': ['sendwelcomemail', 'welcomemail', 'tickets', 'queuepartitioning', 'initial_common_countries']},
        {'id': 'promo', 'legend': 'Website promotion', 'fields': ['promoactive', 'promotext', 'promopicurl']},
        {'id': 'twitter', 'legend': 'Twitter settings', 'fields': ['twitter_timewindow_start', 'twitter_timewindow_end', 'twitter_postpolicy', ]},
        {'id': 'fields', 'legend': 'Registration fields', 'fields': ['asktshirt', 'askfood', 'asknick', 'asktwitter', 'askbadgescan', 'askshareemail', 'askphotoconsent', 'additionalintro', ]},
        {'id': 'steps', 'legend': 'Steps', 'fields': ['registrationopen', 'registrationtimerange', 'allowedit', 'callforpapersopen', 'callforpaperstimerange', 'callforsponsorsopen', 'callforsponsorstimerange', 'scheduleactive', 'sessionsactive', 'cardsactive', 'checkinactive', 'conferencefeedbackopen', 'feedbackopen']},
        {'id': 'callforpapers', 'legend': 'Call for papers', 'fields': ['skill_levels', 'callforpaperstags', 'callforpapersintro', 'showvotes']},
        {'id': 'roles', 'legend': 'Roles', 'fields': ['testers', 'talkvoters', 'staff', 'volunteers', 'checkinprocessors', ]},
        {'id': 'display', 'legend': 'Display', 'fields': ['jinjaenabled', ]},
        {'id': 'legacy', 'legend': 'Legacy', 'fields': ['schedulewidth', 'pixelsperminute']},
    ]

    def clean(self):
        cleaned_data = super(BackendConferenceForm, self).clean()
        if cleaned_data.get('sendwelcomemail') and not cleaned_data.get('welcomemail'):
            self.add_error('welcomemail', 'When send welcome mail is specified, welcome mail contents are mandatory!')

        if cleaned_data.get('tickets') and not cleaned_data.get('sendwelcomemail'):
            self.add_error('tickets', 'If tickets should be generated and sent, welcome emails must be sent!')

        if cleaned_data.get('checkinactive') and not cleaned_data.get('tickets'):
            self.add_error('checkinactive', 'Check-in cannot be activated if tickets are not used!')

        return cleaned_data

    def clean_jinjaenabled(self):
        je = self.cleaned_data.get('jinjaenabled', False)
        if je:
            if not self.instance.jinjadir:
                raise ValidationError("Jinja templates cannot be enabled since there is no Jinja directory configured in superuser sesttings")
        return je


def _timezone_choices():
    return [(z, z) for z in pytz.all_timezones]


class BackendSuperConferenceForm(BackendForm):
    tzname = django.forms.ChoiceField(choices=_timezone_choices(), label='Time zone')

    helplink = 'super_conference#conferenceform'
    selectize_multiple_fields = {
        'administrators': GeneralAccountLookup(),
    }
    selectize_single_fields = {
        'tzname': None,
    }
    accounting_object = django.forms.ChoiceField(choices=[], required=False)
    exclude_date_validators = ['startdate', 'enddate']

    class Meta:
        model = Conference
        fields = ['conferencename', 'urlname', 'series', 'startdate', 'enddate', 'location',
                  'tzname', 'contactaddr', 'sponsoraddr', 'notifyaddr', 'confurl', 'administrators',
                  'jinjadir', 'accounting_object', 'vat_registrations', 'vat_sponsorship',
                  'paymentmethods', 'web_origins']
        widgets = {
            'paymentmethods': django.forms.CheckboxSelectMultiple,
        }
        fieldsets = [
            {'id': 'base_info', 'legend': 'Basic information', 'fields': ['conferencename', 'urlname', 'series', 'location', 'confurl',
                                                                          'jinjadir', 'administrators']},
            {'id': 'time', 'legend': 'Timing information', 'fields': ['startdate', 'enddate', 'tzname']},
            {'id': 'contact', 'legend': 'Contact information', 'fields': ['contactaddr', 'sponsoraddr', 'notifyaddr']},
            {'id': 'financial', 'legend': 'Financial information', 'fields': ['accounting_object', 'vat_registrations',
                                                                              'vat_sponsorship', 'paymentmethods']},
            {'id': 'api', 'legend': 'API access', 'fields': ['web_origins', ]}
        ]

    def fix_fields(self):
        self.fields['paymentmethods'].label_from_instance = lambda x: "{0}{1}".format(x.internaldescription, x.active and " " or " (INACTIVE)")
        self.fields['accounting_object'].choices = [('', '----'), ] + [(o.name, o.name) for o in postgresqleu.accounting.models.Object.objects.filter(active=True)]
        if not self.instance.id:
            self.remove_field('accounting_object')

    def pre_create_item(self):
        # Create a new accounting object automatically if one does not exist already
        (obj, created) = postgresqleu.accounting.models.Object.objects.get_or_create(name=self.instance.urlname,
                                                                                     defaults={'active': True})
        self.instance.accounting_object = obj

    def post_save(self):
        # If we haven't got an RSA key for this conference yet, create it here
        if not self.instance.key_public:
            self.instance.key_private, self.instance.key_public = generate_rsa_keypair()
            self.instance.save(update_fields=['key_private', 'key_public'])

    def clean_tzname(self):
        # The entry for timezone is already validated against the pytz setup which should
        # normally be the same as the one in PostgreSQL, but we verify it against the
        # database side as well to be safe.
        if not exec_to_scalar("SELECT name FROM pg_timezone_names WHERE name=%(name)s", {
                'name': self.cleaned_data['tzname'],
        }):
            raise ValidationError("This timezone does not to exist in the database")

        return self.cleaned_data['tzname']

    def clean_web_origins(self):
        for o in self.cleaned_data['web_origins'].split(','):
            if o == '':
                continue
            try:
                p = urlparse(o.strip())
            except Exception:
                raise ValidationError("Could not parse url {}".format(o))
            if not p.scheme or not p.netloc:
                raise ValidationError("Incomplete url {}".format(o))

        # Re-join string without any spaces
        return ",".join(o.strip() for o in self.cleaned_data['web_origins'].split(','))


class BackendConferenceSeriesForm(BackendForm):
    helplink = "series"
    list_fields = ['name', 'visible', 'sortkey', ]
    markdown_fields = ['intro', ]
    selectize_multiple_fields = {
        'administrators': GeneralAccountLookup(),
    }

    class Meta:
        model = ConferenceSeries
        fields = ['name', 'sortkey', 'visible', 'administrators', 'intro', ]


class BackendTshirtSizeForm(BackendForm):
    helplink = "meta"
    list_fields = ['shirtsize', 'sortkey', ]

    class Meta:
        model = ShirtSize
        fields = ['shirtsize', 'sortkey', ]


class BackendRegistrationForm(BackendForm):
    helplink = "registrations"

    class Meta:
        model = ConferenceRegistration
        fields = ['firstname', 'lastname', 'email', 'company', 'address', 'country', 'phone',
                  'shirtsize', 'dietary', 'twittername', 'nick', 'badgescan', 'shareemail',
                  'regtype', 'additionaloptions']
        fieldsets = [
            {'id': 'personal_info', 'legend': 'Personal information', 'fields': ['firstname', 'lastname', 'email', 'company', 'address', 'country', 'phone', 'twittername', 'nick']},
            {'id': 'reg_info', 'legend': 'Registration information', 'fields': ['regtype', 'additionaloptions', 'badgescan', 'shareemail']},
            {'id': 'attendee_specifics', 'legend': 'Attendee specifics', 'fields': ['shirtsize', 'dietary', ]},
        ]

    def fix_fields(self):
        if self.instance.canceledat:
            self.warning_text = "WARNING! This registration has already been CANCELED! Edit with caution!"
        elif self.instance.payconfirmedat:
            self.warning_text = "WARNING! This registration has already been completed! Edit with caution!"

        self.fields['additionaloptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference)
        self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.conference)
        if not self.conference.askfood:
            self.remove_field('dietary')
        if not self.conference.asktshirt:
            self.remove_field('shirtsize')
        if not self.conference.askbadgescan:
            self.remove_field('badgescan')
        if not self.conference.askshareemail:
            self.remove_field('shareemail')
        self.update_protected_fields()


class BackendRegistrationClassForm(BackendForm):
    helplink = 'registrations#regclasses'
    list_fields = ['regclass', 'badgecolor', 'badgeforegroundcolor']
    allow_copy_previous = True

    class Meta:
        model = RegistrationClass
        fields = ['regclass', 'badgecolor', 'badgeforegroundcolor']

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist):
        # Registration classes are copied straight over, but we disallow duplicates
        for id in idlist:
            source = RegistrationClass.objects.get(conference=sourceconf, pk=id)
            if RegistrationClass.objects.filter(conference=targetconf, regclass=source.regclass).exists():
                yield 'A registration class with name {0} already exists.'.format(source.regclass)
            else:
                RegistrationClass(conference=targetconf,
                                  regclass=source.regclass,
                                  badgecolor=source.badgecolor,
                                  badgeforegroundcolor=source.badgeforegroundcolor).save()


class BackendRegistrationTypeForm(BackendForm):
    helplink = 'registrations#regtypes'
    list_fields = ['regtype', 'regclass', 'cost', 'active', 'sortkey']
    queryset_select_related = ['regclass', ]
    exclude_date_validators = ['activeuntil', ]
    vat_fields = {'cost': 'reg'}
    allow_copy_previous = True
    coltypes = {
        'Sortkey': ['nosearch', ],
    }
    defaultsort = [['sortkey', 'asc']]
    auto_cascade_delete_to = ['registrationtype_days', 'registrationtype_requires_option']

    class Meta:
        model = RegistrationType
        fields = ['regtype', 'regclass', 'cost', 'active', 'activeuntil', 'days', 'sortkey', 'specialtype', 'require_phone', 'alertmessage', 'invoice_autocancel_hours', 'requires_option', 'upsell_target']

    @classmethod
    def get_column_filters(cls, conference):
        return {
            'Registration class': RegistrationClass.objects.filter(conference=conference),
            'Active': [],
        }

    @classmethod
    def get_assignable_columns(cls, conference):
        return [
            {
                'name': 'regclass',
                'title': 'Registration class',
                'options': [(c.id, c.regclass) for c in RegistrationClass.objects.filter(conference=conference)],
            },
        ]

    def fix_fields(self):
        self.fields['regclass'].queryset = RegistrationClass.objects.filter(conference=self.conference)
        self.fields['requires_option'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference)
        if RegistrationDay.objects.filter(conference=self.conference).exists():
            self.fields['days'].queryset = RegistrationDay.objects.filter(conference=self.conference)
        else:
            self.remove_field('days')
            self.update_protected_fields()

        if not ConferenceAdditionalOption.objects.filter(conference=self.conference).exists():
            self.remove_field('requires_option')
            self.remove_field('upsell_target')
            self.update_protected_fields()

    def clean_cost(self):
        if self.cleaned_data['cost'] > 0 and not self.conference.paymentmethods.exists():
            raise ValidationError("Cannot assign a cost, this conference has no payment methods")

        if self.instance and self.instance.cost != self.cleaned_data['cost']:
            if self.instance.conferenceregistration_set.filter(Q(payconfirmedat__isnull=False) | Q(invoice__isnull=False) | Q(bulkpayment__isnull=False)).exists():
                raise ValidationError("This registration type has been used, so the cost can no longer be changed")

        return self.cleaned_data['cost']

    def clean_specialtype(self):
        if self.cleaned_data['specialtype']:
            validate_special_reg_type_setup(self.cleaned_data['specialtype'], self.cleaned_data)
        return self.cleaned_data['specialtype']

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist):
        # Registration types are copied straight over, but we disallow duplicates. We also
        # have to match the registration class.
        # NOTE! We do *not* attempt to adjust VAT rates!
        for id in idlist:
            source = RegistrationType.objects.get(conference=sourceconf, pk=id)
            if RegistrationType.objects.filter(conference=targetconf, regtype=source.regtype).exists():
                yield 'A registration type with name {0} already exists.'.format(source.regtype)
            else:
                try:
                    if source.regclass:
                        targetclass = RegistrationClass.objects.get(conference=targetconf,
                                                                    regclass=source.regclass.regclass)
                    else:
                        targetclass = None
                    RegistrationType(conference=targetconf,
                                     regtype=source.regtype,
                                     regclass=targetclass,
                                     active=source.active,
                                     # Not copying activeuntil
                                     inlist=source.inlist,
                                     sortkey=source.sortkey,
                                     specialtype=source.specialtype,
                                     # Not copying days
                                     alertmessage=source.alertmessage,
                                     upsell_target=source.upsell_target,
                                     # Not copying invoice_autocancel_hours
                                     # Not copying requires_option
                    ).save()
                except RegistrationClass.DoesNotExist:
                    yield 'Could not find registration class {0} for registration type {1}'.format(
                        source.regclass.regclass, source.regtype)


class BackendRegistrationDayForm(BackendForm):
    helplink = 'registrations#days'
    list_fields = ['day', ]

    class Meta:
        model = RegistrationDay
        fields = ['day', ]

    def clean_day(self):
        if self.instance.id:
            if RegistrationDay.objects.filter(conference=self.conference, day=self.cleaned_data['day']).exclude(id=self.instance.id).exists():
                raise ValidationError("This day already exists for this conference")
        else:
            if RegistrationDay.objects.filter(conference=self.conference, day=self.cleaned_data['day']).exists():
                raise ValidationError("This day already exists for this conference")

        return self.cleaned_data['day']


class AdditionalOptionUserManager(object):
    title = 'Users'
    singular = 'user'

    def get_list(self, instance):
        if instance.id:
            return [(r.id, r.fullname, "{} ({})".format(r.regtype.regtype, r.invoice_status)) for r in instance.conferenceregistration_set.all()]

    def get_form(self):
        return None

    def get_object(self, masterobj, subid):
        try:
            return masterobj.conferenceregistration_set.get(pk=subid)
        except models.DoesNotExist:
            return None


class AdditionalOptionPendingManager(object):
    title = 'Pending additional users'
    singular = 'user'

    def get_list(self, instance):
        if instance.id:
            return [(None, p.reg.fullname, p.invoice_status) for p in instance.pendingadditionalorder_set.all()]

    def get_form(self):
        return None


class BackendAdditionalOptionForm(BackendForm):
    helplink = 'registrations#additionaloptions'
    list_fields = ['name', 'cost', 'maxcount', 'invoice_autocancel_hours']
    linked_objects = OrderedDict({
        '../../regdashboard/list': AdditionalOptionUserManager(),
        '../../addoptorders/': AdditionalOptionPendingManager(),
    })
    vat_fields = {'cost': 'reg'}
    auto_cascade_delete_to = ['registrationtype_requires_option', 'conferenceadditionaloption_requires_regtype',
                              'conferenceadditionaloption_mutually_exclusive', ]
    coltypes = {
        'Maxcount': ['nosearch', ],
    }

    class Meta:
        model = ConferenceAdditionalOption
        fields = ['name', 'cost', 'maxcount', 'public', 'upsellable', 'invoice_autocancel_hours',
                  'requires_regtype', 'mutually_exclusive', 'additionaldays']

    def fix_fields(self):
        self.fields['requires_regtype'].queryset = RegistrationType.objects.filter(conference=self.conference)
        self.fields['mutually_exclusive'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference).exclude(pk=self.instance.pk)
        self.fields['additionaldays'].queryset = RegistrationDay.objects.filter(conference=self.conference)


class BackendTrackForm(BackendForm):
    helplink = 'schedule#tracks'
    list_fields = ['trackname', 'incfp', 'sortkey']
    allow_copy_previous = True
    coltypes = {
        'Sortkey': ['nosearch', ],
    }
    defaultsort = [['sortkey', 'asc']]

    class Meta:
        model = Track
        fields = ['trackname', 'sortkey', 'color', 'fgcolor', 'incfp', 'showcompany', 'speakerreg']

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist):
        # Tracks are copied straight over, but we disallow duplicates
        for id in idlist:
            source = Track.objects.get(conference=sourceconf, pk=id)
            if Track.objects.filter(conference=targetconf, trackname=source.trackname).exists():
                yield 'A track with name {0} already exists.'.format(source.trackname)
            else:
                Track(conference=targetconf,
                      trackname=source.trackname,
                      color=source.color,
                      fgcolor=source.fgcolor,
                      sortkey=source.sortkey,
                      incfp=source.incfp,
                ).save()


class BackendRoomForm(BackendForm):
    helplink = 'schedule#rooms'
    list_fields = ['roomname', 'comment', 'sortkey']
    coltypes = {
        'Sortkey': ['nosearch', ],
    }
    defaultsort = [['sortkey', 'asc']]

    class Meta:
        model = Room
        fields = ['roomname', 'sortkey', 'url', 'availabledays', 'comment']

    def fix_fields(self):
        if RegistrationDay.objects.filter(conference=self.conference).exists():
            self.fields['availabledays'].queryset = RegistrationDay.objects.filter(conference=self.conference)
        else:
            self.remove_field('availabledays')
            self.update_protected_fields()


class BackendTagForm(BackendForm):
    helplink = 'schedule#tags'
    list_fields = ['tag', ]

    class Meta:
        model = ConferenceSessionTag
        fields = ['tag', ]


class BackendTransformConferenceDateTimeForm(django.forms.Form):
    timeshift = django.forms.DurationField(required=True, help_text="Shift all times by this much")

    def __init__(self, source, target, *args, **kwargs):
        self.source = source
        self.target = target
        super(BackendTransformConferenceDateTimeForm, self).__init__(*args, **kwargs)
        self.fields['timeshift'].initial = self.source.startdate - self.target.startdate

    def confirm_value(self):
        return str(self.cleaned_data['timeshift'])


class BackendRefundPatternForm(BackendForm):
    helplink = 'registrations'
    list_fields = ['fromdate', 'todate', 'percent', 'fees', ]
    list_order_by = (F('fromdate').asc(nulls_first=True), 'todate', 'percent')
    exclude_date_validators = ['fromdate', 'todate', ]
    allow_copy_previous = True
    copy_transform_form = BackendTransformConferenceDateTimeForm

    class Meta:
        model = RefundPattern
        fields = ['percent', 'fees', 'fromdate', 'todate', ]

    def clean(self):
        cleaned_data = super(BackendRefundPatternForm, self).clean()
        if cleaned_data['fromdate'] and cleaned_data['todate']:
            if cleaned_data['todate'] < cleaned_data['fromdate']:
                self.add_error('todate', 'To date must be after from date!')
        return cleaned_data

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        for id in idlist:
            source = RefundPattern.objects.get(conference=sourceconf, pk=id)
            RefundPattern(conference=targetconf,
                          percent=source.percent,
                          fees=source.fees,
                          fromdate=source.fromdate and source.fromdate + xform or None,
                          todate=source.todate and source.todate + xform or None,
            ).save()
        return
        yield None  # Turn this into a generator

    @classmethod
    def get_transform_example(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        if not idlist:
            return None
        s = RefundPattern.objects.filter(conference=sourceconf, todate__isnull=False)[0]
        return "date {0} becomes {1}".format(
            s.todate, s.todate + xform)


class ConferenceSessionSlideForm(BackendForm):
    helplink = 'callforpapers#slides'
    exclude_fields_from_validation = ['content', ]
    formnote = 'Either enter an URL or upload a PDF file (not both)'

    class Meta:
        model = ConferenceSessionSlides
        fields = ['url', 'content', ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.override_filename = 'unknown_pdf.pdf'
        if 'files' in kwargs:
            if 'content' in kwargs['files']:
                self.override_filename = kwargs['files']['content'].name

    def clean(self):
        d = super().clean()
        url = d.get('url', None)
        pdf = d.get('content', None)

        if url and pdf:
            self.add_error('url', 'Cannot both specify URL and upload PDF!')
            self.add_error('content', 'Cannot both specify URL and upload PDF!')
        elif not (url or pdf):
            self.add_error('url', 'Must either specify URL or upload PDF')
            self.add_error('content', 'Must either specify URL or upload PDF')

        if url:
            self.override_name = url
        else:
            self.override_name = self.override_filename
        print("Set override to %s" % self.override_name)

        return d

    def post_save(self):
        if self.instance.name != self.override_name:
            self.instance.name = self.override_name
            self.instance.save(update_fields=['name', ])


class ConferenceSessionSlideManager(object):
    title = 'Slides'
    singular = 'slide'
    can_add = True

    def get_list(self, instance):
        return [(s.id, s.name, '') for s in instance.conferencesessionslides_set.all()]

    def get_form(self, obj, POST):
        return ConferenceSessionSlideForm

    def get_object(self, masterobj, subid):
        try:
            return ConferenceSessionSlides.objects.get(session=masterobj, pk=subid)
        except ConferenceSessionSlides.DoesNotExist:
            return None

    def get_instancemaker(self, masterobj):
        return lambda: ConferenceSessionSlides(session=masterobj)


class BackendConferenceSessionForm(BackendForm):
    helplink = 'schedule#sessions'
    list_fields = ['title', 'q_speaker_list', 'q_status_string', 'starttime', 'track', 'room', 'cross_schedule']
    verbose_field_names = {
        'q_speaker_list': 'Speakers',
        'q_status_string': 'Status',
        'cross_schedule': 'Cross sched',
    }
    queryset_extra_fields = {
        'q_status_string': "(SELECT statustext FROM confreg_status_strings css WHERE css.id=status)",
        'q_speaker_list': "(SELECT string_agg(spk.fullname, ', ') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=confreg_conferencesession.id)",
    }
    selectize_multiple_fields = {
        'speaker': SpeakerLookup(),
        'tags': SessionTagLookup(None),
    }
    linked_objects = OrderedDict({
        'slides': ConferenceSessionSlideManager(),
    })
    markdown_fields = ['abstract', ]
    allow_copy_previous = True
    copy_transform_form = BackendTransformConferenceDateTimeForm
    auto_cascade_delete_to = ['conferencesession_speaker', 'conferencesessionvote']
    allow_email = True

    class Meta:
        model = ConferenceSession
        fields = ['title', 'htmlicon', 'speaker', 'status', 'starttime', 'endtime', 'cross_schedule',
                  'track', 'room', 'can_feedback', 'skill_level', 'tags', 'abstract', 'submissionnote',
                  'internalnote', ]

    def fix_fields(self):
        self.fields['track'].queryset = Track.objects.filter(conference=self.conference)
        self.fields['room'].queryset = Room.objects.filter(conference=self.conference)

        if self.instance.status != self.instance.lastnotifiedstatus and self.instance.speaker.exists():
            self.fields['status'].help_text = '<b>Warning!</b> This session has <a href="/events/admin/{0}/sessionnotifyqueue/">pending notifications</a> that have not been sent. You probably want to make sure those are sent before editing the status!'.format(self.conference.urlname)

        if not self.conference.skill_levels:
            self.remove_field('skill_level')
            self.update_protected_fields()

        if not self.conference.callforpaperstags:
            self.remove_field('tags')
            if 'tags' in self.selectize_multiple_fields:
                del self.selectize_multiple_fields['tags']
            self.update_protected_fields()
        else:
            self.selectize_multiple_fields['tags'] = SessionTagLookup(self.conference)

    @classmethod
    def get_column_filters(cls, conference):
        return {
            'Status': [v for k, v in STATUS_CHOICES],
            'Track': Track.objects.filter(conference=conference),
            'Room': Room.objects.filter(conference=conference),
            'Cross sched': ['true', 'false', ],
        }

    @classmethod
    def get_assignable_columns(cls, conference):
        return [
            {
                'name': 'track',
                'title': 'Track',
                'options': [(t.id, t.trackname) for t in Track.objects.filter(conference=conference)],
            },
            {
                'name': 'room',
                'title': 'Room',
                'options': [(r.id, r.roomname) for r in Room.objects.filter(conference=conference)],
            },
            {
                'name': 'cross_schedule',
                'title': 'Cross schedule',
                'options': [(1, 'Yes'), (0, 'No'), ]
            },
        ]

    def clean(self):
        cleaned_data = super(BackendConferenceSessionForm, self).clean()

        if cleaned_data.get('starttime') and not cleaned_data.get('endtime'):
            self.add_error('endtime', 'End time must be specified if start time is!')
        elif cleaned_data.get('endtime') and not cleaned_data.get('starttime'):
            self.add_error('starttime', 'Start time must be specified if end time is!')
        elif cleaned_data.get('starttime') and cleaned_data.get('endtime'):
            if cleaned_data.get('endtime') < cleaned_data.get('starttime'):
                self.add_error('endtime', 'End time must be later than start time!')

        if cleaned_data.get('cross_schedule') and cleaned_data.get('room'):
            self.add_error('room', 'Room cannot be specified for cross schedule sessions!')

        return cleaned_data

    def clean_status(self):
        newstatus = self.cleaned_data.get('status')
        if newstatus == self.instance.status:
            return newstatus

        # If there are speakers on the session, we lock it to the workflow. For sessions
        # with no speakers, anything goes
        if not self.cleaned_data.get('speaker').exists():
            return newstatus

        if newstatus not in valid_status_transitions[self.instance.status]:
            raise ValidationError("Sessions with speaker cannot change from {0} to {1}. Only one of {2} is allowed.".format(
                get_status_string(self.instance.status),
                get_status_string(newstatus),
                ", ".join(["{0} ({1})".format(get_status_string(s), v) for s, v in list(valid_status_transitions[self.instance.status].items())]),
            ))

        return newstatus

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        for id in idlist:
            source = ConferenceSession.objects.get(conference=sourceconf, pk=id)
            try:
                if source.track:
                    targettrack = Track.objects.get(conference=targetconf,
                                                    trackname=source.track.trackname)
                else:
                    targettrack = None
                s = ConferenceSession(conference=targetconf,
                                      title=source.title,
                                      starttime=source.starttime and source.starttime + xform,
                                      endtime=source.starttime and source.endtime + xform,
                                      track=targettrack,
                                      cross_schedule=source.cross_schedule,
                                      can_feedback=source.can_feedback,
                                      abstract=source.abstract,
                                      skill_level=source.skill_level,
                                      status=0,
                                      submissionnote=source.submissionnote,
                                      internalnote=source.internalnote,
                                      initialsubmit=source.initialsubmit,
                                      htmlicon=source.htmlicon,
                )
                s.save()
                for spk in source.speaker.all():
                    s.speaker.add(spk)

            except Track.DoesNotExist:
                yield 'Could not find track {0}'.format(source.track.trackname)

    @classmethod
    def get_transform_example(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        slotlist = ConferenceSession.objects.filter(conference=sourceconf, id__in=idlist, starttime__isnull=False)[:2]
        if slotlist:
            return " and ".join(["time {0} becomes {1}".format(s.starttime, s.starttime + xform) for s in slotlist])

        # Do we have sessions without time?
        slotlist = ConferenceSession.objects.filter(conference=sourceconf, id__in=idlist)
        if slotlist:
            return "no scheduled sessions picked, so no transformation will happen"
        return None


class BackendSpeakerForm(BackendForm):
    helplink = 'schedule#speakers'
    list_fields = ['fullname', 'user', 'company', ]
    markdown_fields = ['abstract', ]
    readonly_fields = ['user', ]
    exclude_fields_from_validation = ['user', 'photo512', ]
    # We must save the photo field as well, since it's being updaed in the pre_save signal,
    # and we want to include that updating.
    extra_update_fields = ['photo', ]

    class Meta:
        model = Speaker
        fields = ['fullname', 'user', 'twittername', 'company', 'abstract', 'photo512', ]
        widgets = {
            'user': StaticTextWidget,
        }

        @classmethod
        def conference_queryset(cls, conference):
            # Ugly because django can't properly do exists
            return Speaker.objects.extra(
                where=("EXISTS (SELECT 1 FROM confreg_conferencesession_speaker css INNER JOIN confreg_conferencesession s ON s.id=css.conferencesession_id WHERE css.speaker_id=confreg_speaker.id AND s.conference_id=%s)", ),
                params=(conference.id, ),
            )

    def fix_fields(self):
        self.initial['user'] = escape(self.instance._display_user())


class BackendConferenceSessionSlotForm(BackendForm):
    helplink = 'schedule#slots'
    list_fields = ['starttime', 'endtime', ]
    allow_copy_previous = True
    copy_transform_form = BackendTransformConferenceDateTimeForm

    class Meta:
        model = ConferenceSessionScheduleSlot
        fields = ['starttime', 'endtime', ]

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        for id in idlist:
            source = ConferenceSessionScheduleSlot.objects.get(conference=sourceconf, pk=id)
            ConferenceSessionScheduleSlot(conference=targetconf,
                                          starttime=source.starttime + xform,
                                          endtime=source.endtime + xform,
                                          ).save()
        return
        yield None  # Turn this into a generator

    @classmethod
    def get_transform_example(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        slotlist = [ConferenceSessionScheduleSlot.objects.get(conference=sourceconf, id=i) for i in idlist[:2]]
        xstr = " and ".join(["time {0} becomes {1}".format(s.starttime, s.starttime + xform) for s in slotlist])
        return xstr


class BackendVolunteerSlotForm(BackendForm):
    helplink = 'volunteers#slots'
    list_fields = ['timerange', 'title', 'min_staff', 'max_staff', ]
    allow_copy_previous = True
    copy_transform_form = BackendTransformConferenceDateTimeForm

    class Meta:
        model = VolunteerSlot
        fields = ['timerange', 'title', 'min_staff', 'max_staff', ]
    coltypes = {
        'Min staff': ['nosearch', ],
        'Max staff': ['nosearch', ],
    }

    def clean(self):
        cleaned_data = super(BackendVolunteerSlotForm, self).clean()
        if cleaned_data.get('min_staff') > cleaned_data.get('max_staff'):
            self.add_error('max_staff', 'Max staff must be at least as high as min_staff!')

        return cleaned_data

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        for id in idlist:
            source = VolunteerSlot.objects.get(conference=sourceconf, pk=id)
            VolunteerSlot(conference=targetconf,
                          timerange=DateTimeTZRange(source.timerange.lower + xform,
                                                    source.timerange.upper + xform),
                          title=source.title,
                          min_staff=source.min_staff,
                          max_staff=source.max_staff,
            ).save()
        return
        yield None  # Turn this into a generator

    @classmethod
    def get_transform_example(self, targetconf, sourceconf, idlist, transformform):
        xform = transformform.cleaned_data['timeshift']
        if not idlist:
            return None
        s = VolunteerSlot.objects.get(conference=sourceconf, id=idlist[0])
        return "range {0}-{1} becomes {2}-{3}".format(
            s.timerange.lower, s.timerange.upper,
            s.timerange.lower + xform, s.timerange.upper + xform,
        )


class BackendFeedbackQuestionForm(BackendForm):
    helplink = 'feedback#conference'
    list_fields = ['newfieldset', 'question', 'sortkey', ]
    allow_copy_previous = True

    class Meta:
        model = ConferenceFeedbackQuestion
        fields = ['question', 'isfreetext', 'textchoices', 'sortkey', 'newfieldset']

    coltypes = {
        'Sortkey': ['nosearch', ],
        'Newfieldset': ['nosort', ],
    }
    defaultsort = [['sortkey', 'asc']]

    def clean(self):
        cleaned_data = super(BackendFeedbackQuestionForm, self).clean()
        if not self.cleaned_data.get('isfreetext', 'False'):
            if self.cleaned_data.get('textchoices', ''):
                self.add_error('textchoices', 'Textchoices can only be specified for freetext fields')
        return cleaned_data

    def clean_textchoices(self):
        val = self.cleaned_data['textchoices']
        if val:
            if ';' not in val:
                if ':' in val:
                    raise ValidationError('When choices are used, more than one option must be specified! It looks like you may have used colon instead of semicolon to separate values.')
                else:
                    raise ValidationError('When choices are used, than one must be specified!')
        return val

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist):
        # Conference feedback questions are copied straight over, but we disallow duplicates
        for id in idlist:
            source = ConferenceFeedbackQuestion.objects.get(conference=sourceconf, pk=id)
            if ConferenceFeedbackQuestion.objects.filter(conference=targetconf, question=source.question).exists():
                yield 'A question {0} already exists.'.format(source.question)
            else:
                ConferenceFeedbackQuestion(conference=targetconf,
                                           question=source.question,
                                           isfreetext=source.isfreetext,
                                           textchoices=source.textchoices,
                                           sortkey=source.sortkey,
                                           newfieldset=source.newfieldset,
                                           ).save()


class BackendNewDiscountCodeForm(django.forms.Form):
    helplink = 'vouchers#discountcodes'
    codetype = django.forms.ChoiceField(choices=((1, 'Fixed amount discount'), (2, 'Percentage discount')))

    def get_newform_data(self):
        return self.cleaned_data['codetype']


class DiscountCodeUserManager(object):
    title = 'Users'
    singular = 'user'

    def get_list(self, instance):
        if instance.code:
            return [(r.id, r.fullname, "{} ({})".format(r.regtype.regtype, r.invoice_status)) for r in ConferenceRegistration.objects.filter(conference=instance.conference, vouchercode=instance.code)]
        return []

    def get_form(self):
        return None

    def get_object(self, masterobj, subjid):
        try:
            return ConferenceRegistration.objects.get(discountcode=blah, pk=subjid)
        except ConferenceRegistration.DoesNotExist:
            return None


class BackendDiscountCodeForm(BackendForm):
    helplink = 'vouchers#discountcodes'
    list_fields = ['code', 'validuntil', 'maxuses', 'public']
    linked_objects = OrderedDict({
        '../../regdashboard/list': DiscountCodeUserManager(),
    })

    form_before_new = BackendNewDiscountCodeForm

    exclude_date_validators = ['validuntil', ]

    class Meta:
        model = DiscountCode
        fields = ['code', 'discountamount', 'discountpercentage', 'regonly', 'public', 'validuntil', 'maxuses',
                  'requiresregtype', 'requiresoption']

    def fix_fields(self):
        if self.newformdata == "1" and not self.instance.discountamount:
            self.instance.discountamount = 1
        elif self.newformdata == "2" and not self.instance.discountpercentage:
            self.instance.discountpercentage = 1

        if self.instance.discountamount:
            # Fixed amount discount
            self.remove_field('discountpercentage')
            self.remove_field('regonly')
            self.fields['discountamount'].validators.append(MinValueValidator(1))
        else:
            # Percentage discount
            self.remove_field('discountamount')
            self.fields['discountpercentage'].validators.extend([
                MinValueValidator(1),
                MaxValueValidator(99),
            ])
        self.fields['maxuses'].validators.append(MinValueValidator(0))

        self.fields['requiresregtype'].queryset = RegistrationType.objects.filter(conference=self.conference)
        self.fields['requiresoption'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference).exclude(pk=self.instance.pk)

        self.update_protected_fields()

    def clean_code(self):
        if self.instance.id:
            if DiscountCode.objects.filter(conference=self.conference, code=self.cleaned_data['code']).exclude(id=self.instance.id).exists():
                raise ValidationError("This discount code already exists for this conference")
        else:
            if DiscountCode.objects.filter(conference=self.conference, code=self.cleaned_data['code']).exists():
                raise ValidationError("This discount code already exists for this conference")

        return self.cleaned_data['code']


class BackendAccessTokenForm(BackendForm):
    helplink = 'tokens'
    list_fields = ['token', 'description', 'permissions', ]
    readonly_fields = ['token', ]

    class Meta:
        model = AccessToken
        fields = ['token', 'description', 'permissions', ]

    def _transformed_accesstoken_permissions(self):
        for k, v in AccessTokenPermissions:
            baseurl = '/events/admin/{0}/tokendata/{1}/{2}'.format(self.conference.urlname, self.instance.token, k)
            formats = ['csv', 'tsv', 'json', ]
            yield k, mark_safe('{0} ({1})'.format(v, ", ".join(['<a href="{0}.{1}">{1}</a>'.format(baseurl, f) for f in formats])))

    def fix_fields(self):
        self.fields['permissions'].widget = django.forms.CheckboxSelectMultiple(
            choices=self._transformed_accesstoken_permissions(),
        )

    @classmethod
    def get_initial(self):
        return {
            'token': generate_random_token()
        }


class BackendNewsForm(BackendForm):
    helplink = 'news'
    list_fields = ['title', 'datetime', 'author', ]
    queryset_select_related = ['author', ]
    markdown_fields = ['summary', ]
    exclude_date_validators = ['datetime', ]
    defaultsort = [['datetime', "desc"]]

    class Meta:
        model = ConferenceNews
        fields = ['author', 'datetime', 'title', 'inrss', 'summary', ]

    def fix_fields(self):
        # Must be administrator on current conference
        self.fields['author'].queryset = NewsPosterProfile.objects.filter(author__conference=self.conference)
        # Add help hint dynamically so we can include the conference name
        self.fields['title'].help_text = 'Note! Title will be prefixed with "{0} - " on shared frontpage and RSS!'.format(self.conference.conferencename)


class BackendMessagingForm(BackendForm):
    helplink = 'integrations#messaging'
    list_fields = ['providername', 'broadcast', 'privatebcast', 'notification', 'orgnotification']
    verbose_field_names = {
        'providername': 'Provider name',
    }
    queryset_extra_fields = {
        'providername': '(SELECT internalname FROM confreg_messagingprovider WHERE id=confreg_conferencemessaging.provider_id)',
    }

    @property
    def fieldsets(self):
        fs = [
            {'id': 'provider', 'legend': 'Provider', 'fields': ['provider', ]},
            {'id': 'actions', 'legend': 'Actions', 'fields': ['broadcast', 'privatebcast', 'notification', 'orgnotification']},
        ]
        cf = list(self._channel_fields())
        if cf:
            fs.append(
                {'id': 'channels', 'legend': 'Channels/Groups', 'fields': list(self._channel_fields())}
            )
        return fs

    class Meta:
        model = ConferenceMessaging
        fields = ['provider', 'broadcast', 'privatebcast', 'notification', 'orgnotification', ]

    def _channel_fields(self):
        for fld in ('privatebcast', 'orgnotification'):
            if getattr(self.impl, 'can_{}'.format(fld), False):
                yield '{}channel'.format(fld)

    @property
    def readonly_fields(self):
        yield 'provider'
        for fld in ('broadcast', 'privatebcast', 'notification', 'orgnotification'):
            if not getattr(self.impl, 'can_{}'.format(fld), False):
                yield fld
        yield from self._channel_fields()

    def __init__(self, *args, **kwargs):
        self.impl = get_messaging(kwargs['instance'].provider)
        if hasattr(self.impl, 'refresh_messaging_config'):
            if self.impl.refresh_messaging_config(kwargs['instance'].config):
                kwargs['instance'].save(update_fields=['config'])
        super().__init__(*args, **kwargs)

    _channel_fieldnames = {
        'privatebcast': 'Attendee only broadcast channel',
        'orgnotification': 'Organisation notification channel',
    }

    def fix_fields(self):
        super().fix_fields()
        self.fields['provider'].widget.attrs['disabled'] = True
        self.fields['provider'].required = False

        # Update the different types of supported fields
        for fld in ('broadcast', 'privatebcast', 'notification', 'orgnotification'):
            if not getattr(self.impl, 'can_{}'.format(fld), False):
                self.fields[fld].widget.attrs['disabled'] = True
                self.fields[fld].help_text = 'Action is not supported by this provider'

        for fld in ('privatebcast', 'orgnotification'):
            if getattr(self.impl, 'can_{}'.format(fld), False):
                self.fields['{}channel'.format(fld)] = self.impl.get_channel_field(self.instance, fld)
                self.fields['{}channel'.format(fld)].label = self._channel_fieldnames[fld]
                self.fields['{}channel'.format(fld)].required = False


class BackendSeriesMessagingNewForm(django.forms.Form):
    helplink = 'integrations#provider'
    classname = SelectSetValueField(choices=messaging_implementation_choices(),
                                    setvaluefield='baseurl', label='Implementation class')
    baseurl = django.forms.URLField(label='Base URL')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_newform_data(self):
        return '{}:{}'.format(self.cleaned_data['classname'], self.cleaned_data['baseurl'])

    def clean_baseurl(self):
        return self.cleaned_data['baseurl'].rstrip('/')

    def clean(self):
        d = super().clean()
        if 'classname' in d and 'baseurl' in d:
            # Both fields specified, so verify they're an allowed combination
            r = get_messaging_class(d['classname']).validate_baseurl(d['baseurl'])
            if r:
                self.add_error('baseurl', r)
        return d


class BackendSeriesMessagingForm(BackendForm):
    helplink = 'integrations#provider'
    list_fields = ['internalname', 'publicname', 'active', 'route_incoming', 'classname_short', ]
    queryset_select_related = ['route_incoming', ]
    form_before_new = BackendSeriesMessagingNewForm
    verbose_field_names = {
        'classname_short': 'Implementation',
    }
    queryset_extra_fields = {
        'classname_short': r"substring(classname, '[^\.]+$')",
    }
    auto_cascade_delete_to = ['conferencemessaging', ]

    config_fields = []
    config_fieldsets = []
    config_readonly_fields = []

    process_incoming = False
    no_incoming_processing = False

    class Meta:
        model = MessagingProvider
        fields = ['internalname', 'publicname', 'active', 'classname', 'route_incoming']

    @property
    def readonly_fields(self):
        return ['classname', ] + self.config_readonly_fields

    @property
    def json_form_fields(self):
        return {
            'config': self.config_fields,
        }

    @property
    def fieldsets(self):
        fs = [
            {'id': 'common', 'legend': 'Common', 'fields': ['internalname', 'publicname', 'active', 'classname'], },
        ]
        if self.process_incoming:
            fs.append(
                {'id': 'incoming', 'legend': 'Incoming', 'fields': ['route_incoming', ], }
            )

        return fs + self.config_fieldsets

    def fix_fields(self):
        super().fix_fields()
        if self.newformdata:
            classname, baseurl = self.newformdata.split(':', 1)
            self.instance.classname = classname
            self.initial['classname'] = classname
            self.baseurl = baseurl

        impl = get_messaging_class(self.instance.classname)
        if getattr(impl, 'can_process_incoming', False) and not self.no_incoming_processing:
            self.process_incoming = True
            self.fields['route_incoming'].queryset = Conference.objects.filter(series=self.instance.series)
            self.fields['route_incoming'].help_text = 'Incoming messages from this provider will be added to the specified conference'
        else:
            del self.fields['route_incoming']
            self.update_protected_fields()


#
# Form to pick a conference to copy from
#
class BackendCopySelectConferenceForm(django.forms.Form):
    conference = django.forms.ModelChoiceField(Conference.objects.all())

    def __init__(self, request, conference, model, *args, **kwargs):
        super(BackendCopySelectConferenceForm, self).__init__(*args, **kwargs)
        self.fields['conference'].queryset = Conference.objects.filter(Q(administrators=request.user) | Q(series__administrators=request.user)).exclude(pk=conference.pk).extra(
            where=["EXISTS (SELECT 1 FROM {0} WHERE conference_id=confreg_conference.id)".format(model._meta.db_table), ]
        ).distinct()


#
# Form for twitter integration
#
class BackendTweetQueueForm(BackendForm):
    helplink = 'integrations#broadcast'
    list_fields = ['datetime', 'contents', 'author', 'approved', 'approvedby', 'sent', 'hasimage', ]
    verbose_field_names = {
        'hasimage': 'Has image',
        'approvedby': 'Approved by',
    }
    exclude_date_validators = ['datetime', ]
    defaultsort = [['sent', 'asc'], ['datetime', 'desc']]
    exclude_fields_from_validation = ['image', ]
    queryset_select_related = ['author', 'approvedby', ]
    queryset_extra_fields = {
        'hasimage': "image is not null and image != ''",
    }
    auto_cascade_delete_to = ['conferencetweetqueue_remainingtosend', ]

    class Meta:
        model = ConferenceTweetQueue
        fields = ['datetime', 'approved', 'contents', 'image']
        widgets = {
            'contents': MonospaceTextarea,
        }

    def __init__(self, *args, **kwargs):
        super(BackendTweetQueueForm, self).__init__(*args, **kwargs)
        self.fields['contents'].widget = TagOptionsTextWidget([h.hashtag for h in ConferenceHashtag.objects.filter(conference=self.conference)])
        if 'class' in self.fields['contents'].widget.attrs:
            self.fields['contents'].widget.attrs['class'] += " textarea-with-charcount"
        else:
            self.fields['contents'].widget.attrs['class'] = "textarea-with-charcount"
        self.fields['contents'].widget.attrs['data-length-function'] = 'shortened_post_length'

        if self.conference:
            lengthstr = 'Maximum lengths are: {}'.format(', '.join(['{}: {}'.format(mess.provider.internalname, get_messaging(mess.provider).max_post_length) for mess in self.conference.conferencemessaging_set.select_related('provider').filter(broadcast=True, provider__active=True)]))
        else:
            lengthstr = 'Maximum lengths are: {}'.format(', '.join(['{}: {}'.format(provider.internalname, get_messaging(provider).max_post_length) for provider in MessagingProvider.objects.filter(series__isnull=True, active=True)]))

        self.fields['contents'].help_text = lengthstr

    def clean_datetime(self):
        if self.instance:
            t = self.cleaned_data['datetime'].time()
            if self.conference and self.conference.twitter_timewindow_start and self.conference.twitter_timewindow_start != datetime.time(0, 0, 0):
                if t < self.conference.twitter_timewindow_start:
                    raise ValidationError("Tweets for this conference cannot be scheduled before {}".format(self.conference.twitter_timewindow_start))
            if self.conference and self.conference.twitter_timewindow_end:
                if t > self.conference.twitter_timewindow_end and self.conference.twitter_timewindow_end != datetime.time(0, 0, 0):
                    raise ValidationError("Tweets for this conference cannot be scheduled after {}".format(self.conference.twitter_timewindow_end))
            return self.cleaned_data['datetime']

    def clean_contents(self):
        d = self.cleaned_data['contents']
        shortlen = get_shortened_post_length(d)

        if self.conference:
            providers = [mess.provider for mess in self.conference.conferencemessaging_set.select_related('provider').filter(broadcast=True, provider__active=True)]
        else:
            providers = MessagingProvider.objects.filter(series__isnull=True, active=True)

        for provider in providers:
            impl = get_messaging(provider)
            if shortlen > impl.max_post_length:
                messages.warning(self.request, "Post will be truncated to {} characters on {}".format(impl.max_post_length, provider.internalname))
        return d

    @classmethod
    def get_assignable_columns(cls, conference):
        return [
            {
                'name': 'approved',
                'title': 'Approval',
                'options': [(1, 'Yes'), (0, 'No'), ]
            },
        ]

    @classmethod
    def get_rowclass(self, obj):
        if obj.sent:
            return "info"
        return None

    @classmethod
    def get_column_filters(cls, conference):
        if conference:
            return {
                'Author': exec_to_single_list('SELECT DISTINCT username FROM confreg_conferencetweetqueue q INNER JOIN auth_user u ON u.id=q.author_id WHERE q.conference_id=%(confid)s', {'confid': conference.id, }),
                'Approved': ['true', 'false'],
                'Approved by': exec_to_single_list('SELECT DISTINCT username FROM confreg_conferencetweetqueue q INNER JOIN auth_user u ON u.id=q.approvedby_id WHERE q.conference_id=%(confid)s', {'confid': conference.id, }),
                'Sent': ['true', 'false'],
            }
        else:
            return {
                'Author': exec_to_single_list('SELECT DISTINCT username FROM confreg_conferencetweetqueue q INNER JOIN auth_user u ON u.id=q.author_id WHERE q.conference_id IS NULL'),
                'Approved': ['true', 'false'],
                'Approved by': exec_to_single_list('SELECT DISTINCT username FROM confreg_conferencetweetqueue q INNER JOIN auth_user u ON u.id=q.approvedby_id WHERE q.conference_id IS NULL'),
                'Sent': ['true', 'false'],
            }


class BackendHashtagForm(BackendForm):
    helplink = 'integrations#broadcast'
    list_fields = ['hashtag', ]

    class Meta:
        model = ConferenceHashtag
        fields = ['hashtag', ]


class TweetCampaignSelectForm(django.forms.Form):
    campaigntype = django.forms.ChoiceField(
        label='Campaign type',
        choices=[(id, c.name) for id, c in allcampaigns],
    )


#
# Form for confirming a registration
#
class ConfirmRegistrationForm(django.forms.Form):
    confirm = django.forms.BooleanField(help_text="Confirm that you want to confirm this registration!<br/>Normaly this is handled by the automated system, and registrations should only be manually confirmed in special cases!")


#
# Form for re-sending welcome email
#
class ResendWelcomeMailForm(django.forms.Form):
    confirm = django.forms.BooleanField(help_text="Confirm that you want to re-send the welcome email for this registration!")


#
# Form for canceling a registration
#
class CancelRegistrationForm(django.forms.Form):
    refund = django.forms.ChoiceField(required=True, label="Method of refund")
    reason = django.forms.CharField(required=True, max_length=100, label="Reason for cancel",
                                    help_text="Copied directly into confirmation emails and refund notices!")
    confirm = django.forms.BooleanField(help_text="Confirm that you want to cancel this registration!")

    class Methods:
        NO_REFUND = -1

    def __init__(self, totalnovat, totalvat, refundchoices, *args, **kwargs):
        self.totalnovat = totalnovat
        self.totalvat = totalvat
        super(CancelRegistrationForm, self).__init__(*args, **kwargs)
        self.fields['refund'].choices = [(None, '-- Select method'), ] + refundchoices

        if 'refund' not in self.data:
            del self.fields['confirm']


#
# Form for canceling a conference invoice
#
class ConferenceInvoiceCancelForm(django.forms.Form):
    reason = django.forms.CharField(max_length=400, min_length=10, required=True, label="Reason for cancel",
                                    help_text="Specify the reason for canceling the invoice. Note that this reason is sent by email to the invoice recipient.")
    confirm = django.forms.BooleanField(help_text="Confirm that you really want to cancel this invoice!")

    def __init__(self, *args, **kwargs):
        super(ConferenceInvoiceCancelForm, self).__init__(*args, **kwargs)

        if 'reason' not in self.data:
            del self.fields['confirm']


#
# Form for refunding a purchased order
#
class PurchasedVoucherRefundForm(django.forms.Form):
    confirm = django.forms.BooleanField(label="Confirm", required=True)


#
# Form for refunding a multi registration
#
class BulkPaymentRefundForm(django.forms.Form):
    amount = django.forms.DecimalField(decimal_places=2, required=False, label="Refund amount (ex VAT)")
    vatamount = django.forms.DecimalField(decimal_places=2, required=False, label="Refund VAT amount")
    confirm = django.forms.BooleanField(label="Confirm", required=True)

    def __init__(self, invoice, *args, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

        total = invoice.total_refunds

        self.fields['amount'].validators = [MinValueValidator(0), MaxValueValidator(total['remaining']['amount'])]
        if total['amount'] > 0:
            self.fields['amount'].help_text = '{}{} of {}{} remains to be refunded on this invoice.'.format(settings.CURRENCY_SYMBOL, total['remaining']['amount'], settings.CURRENCY_SYMBOL, invoice.total_amount - invoice.total_vat)
        else:
            self.fields['amount'].help_text = 'Invoice total value is {}{}'.format(settings.CURRENCY_SYMBOL, invoice.total_amount - invoice.total_vat)

        if not settings.EU_VAT:
            del self.fields['vatamount']
        else:
            self.fields['vatamount'].validators = [MinValueValidator(0), MaxValueValidator(total['remaining']['vatamount'])]
            if total['vatamount'] > 0:
                self.fields['vatamount'].help_text = '{}{} of {}{} remains to be refunded on this invoice.'.format(settings.CURRENCY_SYMBOL, total['remaining']['vatamount'], settings.CURRENCY_SYMBOL, invoice.total_vat)
            else:
                self.fields['vatamount'].help_text = 'Invoice total value is {}{}'.format(settings.CURRENCY_SYMBOL, invoice.total_vat)


#
# Form for sending email
#
class BackendSendEmailForm(django.forms.Form):
    _from = django.forms.CharField(max_length=100, disabled=True, label="From")
    subject = django.forms.CharField(max_length=128, required=True)
    recipients = django.forms.Field(widget=StaticTextWidget, required=False)
    storeonregpage = django.forms.BooleanField(label="Store on registration page", required=False,
                                               help_text="If checked, store in db and show to attendees later. If not checked, one-off email is sent.")
    message = django.forms.CharField(widget=EmailTextWidget, required=True)
    idlist = django.forms.CharField(widget=django.forms.HiddenInput, required=True)
    confirm = django.forms.BooleanField(label="Confirm", required=False)

    def __init__(self, conference, *args, **kwargs):
        super(BackendSendEmailForm, self).__init__(*args, **kwargs)
        self.conference = conference
        if not (self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']

        self.fields['subject'].help_text = 'Subject will be prefixed with <strong>[{}]</strong>'.format(conference)

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")

    def clean_subject(self):
        if not self.cleaned_data['subject']:
            raise ValidationError("Please enter a subject")

        # Max length of subject is 100, but we prefix with [] and a space
        maxlen = 100 - len(str(self.conference)) - 3

        if len(self.cleaned_data['subject']) > maxlen:
            raise ValidationError("Maximum length of subject is {}, to leave room for prefix. You entered {} characters.".format(maxlen, len(self.cleaned_data['subject'])))

        return self.cleaned_data['subject']


class BackendRegistrationDmForm(django.forms.Form):
    message = django.forms.CharField(max_length=500, required=True)

    def __init__(self, maxlength, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if maxlength:
            self.fields['message'].max_length = maxlength
            self.fields['message'].help_text = 'Maximum message length for this provider is {} characters.'.format(maxlength)
