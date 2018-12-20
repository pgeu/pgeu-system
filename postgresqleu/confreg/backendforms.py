from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
import django.forms
import django.forms.widgets
from django.utils.safestring import mark_safe

import datetime
from collections import OrderedDict
from psycopg2.extras import DateTimeTZRange

from postgresqleu.util.forms import ConcurrentProtectedModelForm
from postgresqleu.util.random import generate_random_token
from postgresqleu.util.backendforms import BackendForm

import postgresqleu.accounting.models

from postgresqleu.confreg.models import Conference, ConferenceRegistration, ConferenceAdditionalOption
from postgresqleu.confreg.models import RegistrationClass, RegistrationType, RegistrationDay
from postgresqleu.confreg.models import ConferenceFeedbackQuestion
from postgresqleu.confreg.models import ConferenceSession, Track, Room
from postgresqleu.confreg.models import ConferenceSessionScheduleSlot, VolunteerSlot
from postgresqleu.confreg.models import DiscountCode, AccessToken, AccessTokenPermissions
from postgresqleu.confreg.models import ConferenceSeries
from postgresqleu.confreg.models import ConferenceNews
from postgresqleu.confreg.models import ShirtSize
from postgresqleu.newsevents.models import NewsPosterProfile

from postgresqleu.confreg.models import valid_status_transitions, get_status_string
from postgresqleu.confreg.models import STATUS_CHOICES

from postgresqleu.util.backendlookups import GeneralAccountLookup
from postgresqleu.confreg.backendlookups import RegisteredUsersLookup, SpeakerLookup


class BackendConferenceForm(BackendForm):
    helplink = 'configuring#conferenceform'
    markdown_fields = ['promotext', ]
    selectize_multiple_fields = {
        'testers': GeneralAccountLookup(),
        'talkvoters': GeneralAccountLookup(),
        'staff': GeneralAccountLookup(),
        'volunteers': RegisteredUsersLookup(None),
    }

    class Meta:
        model = Conference
        fields = ['active', 'callforpapersopen', 'callforsponsorsopen', 'feedbackopen',
                  'conferencefeedbackopen', 'scheduleactive', 'sessionsactive', 'allowedit',
                  'promoactive', 'promotext', 'promopicurl',
                  'twitter_timewindow_start', 'twitter_timewindow_end',
                  'schedulewidth', 'pixelsperminute',
                  'testers', 'talkvoters', 'staff', 'volunteers',
                  'asktshirt', 'askfood', 'asknick', 'asktwitter', 'askshareemail', 'askphotoconsent',
                  'skill_levels', 'additionalintro', 'callforpapersintro', 'sendwelcomemail', 'welcomemail',
                  'invoice_autocancel_hours', 'attendees_before_waitlist']

    def fix_fields(self):
        self.selectize_multiple_fields['volunteers'] = RegisteredUsersLookup(self.conference)

    fieldsets = [
        {'id': 'base_info', 'legend': 'Basic information', 'fields': ['attendees_before_waitlist', 'invoice_autocancel_hours', 'sendwelcomemail', 'welcomemail', 'additionalintro']},
        {'id': 'promo', 'legend': 'Website promotion', 'fields': ['promoactive', 'promotext', 'promopicurl']},
        {'id': 'twitter', 'legend': 'Twitter settings', 'fields': ['twitter_timewindow_start', 'twitter_timewindow_end', ]},
        {'id': 'fields', 'legend': 'Registration fields', 'fields': ['asktshirt', 'askfood', 'asknick', 'asktwitter', 'askshareemail', 'askphotoconsent']},
        {'id': 'steps', 'legend': 'Steps', 'fields': ['active', 'allowedit', 'callforpapersopen', 'callforsponsorsopen', 'scheduleactive', 'sessionsactive', 'conferencefeedbackopen', 'feedbackopen']},
        {'id': 'callforpapers', 'legend': 'Call for papers', 'fields': ['skill_levels', 'callforpapersintro']},
        {'id': 'roles', 'legend': 'Roles', 'fields': ['testers', 'talkvoters', 'staff', 'volunteers']},
        {'id': 'legacy', 'legend': 'Legacy', 'fields': ['schedulewidth', 'pixelsperminute']},
    ]


class BackendSuperConferenceForm(BackendForm):
    helplink = 'super_conference#conferenceform'
    selectize_multiple_fields = {
        'administrators': GeneralAccountLookup(),
    }
    accounting_object = django.forms.ChoiceField(choices=[], required=False)
    exclude_date_validators = ['startdate', 'enddate']

    class Meta:
        model = Conference
        fields = ['conferencename', 'urlname', 'series', 'startdate', 'enddate', 'location',
                  'timediff', 'contactaddr', 'sponsoraddr', 'confurl', 'administrators',
                  'jinjadir', 'accounting_object', 'vat_registrations', 'vat_sponsorship', ]

    def fix_fields(self):
        self.fields['accounting_object'].choices = [('', '----'), ] + [(o.name, o.name) for o in postgresqleu.accounting.models.Object.objects.filter(active=True)]
        if not self.instance.id:
            self.remove_field('accounting_object')

    def pre_create_item(self):
        # Create a new accounting object automatically if one does not exist already
        (obj, created) = postgresqleu.accounting.models.Object.objects.get_or_create(name=self.instance.urlname,
                                                                                     defaults={'active': True})
        self.instance.accounting_object = obj


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
    fieldsets = [
        {'id': 'personal_info', 'legend': 'Personal information', 'fields': ['firstname', 'lastname', 'email', 'company', 'address', 'country', 'phone', 'twittername', 'nick']},
        {'id': 'reg_info', 'legend': 'Registration information', 'fields': ['regtype', 'additionaloptions', 'shareemail']},
        {'id': 'attendee_specifics', 'legend': 'Attendee specifics', 'fields': ['shirtsize', 'dietary']},
    ]

    class Meta:
        model = ConferenceRegistration
        fields = ['firstname', 'lastname', 'email', 'company', 'address', 'country', 'phone',
                  'shirtsize', 'dietary', 'twittername', 'nick', 'shareemail',
                  'regtype', 'additionaloptions']

    def fix_fields(self):
        if self.instance.payconfirmedat:
            self.warning_text = "WARNING! This registration has already been completed! Edit with caution!"

        self.fields['additionaloptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference)
        self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.conference)
        if not self.conference.askfood:
            self.remove_field('askfood')
        if not self.conference.asktshirt:
            self.remove_field('shirtsize')
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
    exclude_date_validators = ['activeuntil', ]
    vat_fields = {'cost': 'reg'}
    allow_copy_previous = True
    coltypes = {
        'Sortkey': ['nosearch', ],
    }
    defaultsort = [[4, 'asc']]
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
        if self.instance and self.instance.cost != self.cleaned_data['cost']:
            if self.instance.conferenceregistration_set.filter(Q(payconfirmedat__isnull=False) | Q(invoice__isnull=False) | Q(bulkpayment__isnull=False)).exists():
                raise ValidationError("This registration type has been used, so the cost can no longer be changed")

        return self.cleaned_data['cost']

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


class BackendAdditionalOptionForm(BackendForm):
    helplink = 'registrations#additionaloptions'
    list_fields = ['name', 'cost', 'maxcount', 'invoice_autocancel_hours']
    vat_fields = {'cost': 'reg'}
    auto_cascade_delete_to = ['registrationtype_requires_option', 'conferenceadditionaloption_requires_regtype',
                              'conferenceadditionaloption_mutually_exclusive', ]
    coltypes = {
        'Maxcount': ['nosearch', ],
    }

    class Meta:
        model = ConferenceAdditionalOption
        fields = ['name', 'cost', 'maxcount', 'public', 'upsellable', 'invoice_autocancel_hours',
                  'requires_regtype', 'mutually_exclusive']

    def fix_fields(self):
        self.fields['requires_regtype'].queryset = RegistrationType.objects.filter(conference=self.conference)
        self.fields['mutually_exclusive'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference).exclude(pk=self.instance.pk)


class BackendTrackForm(BackendForm):
    helplink = 'schedule#tracks'
    list_fields = ['trackname', 'sortkey']
    allow_copy_previous = True
    coltypes = {
        'Sortkey': ['nosearch', ],
    }
    defaultsort = [[1, 'asc']]

    class Meta:
        model = Track
        fields = ['trackname', 'sortkey', 'color', 'incfp']

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
                      sortkey=source.sortkey,
                      incfp=source.incfp,
                ).save()


class BackendRoomForm(BackendForm):
    helplink = 'schedule#rooms'
    list_fields = ['roomname', 'sortkey']
    coltypes = {
        'Sortkey': ['nosearch', ],
    }
    defaultsort = [[1, 'asc']]

    class Meta:
        model = Room
        fields = ['roomname', 'sortkey']


class BackendTransformConferenceDateTimeForm(django.forms.Form):
    timeshift = django.forms.DurationField(required=True, help_text="Shift all times by this much")

    def __init__(self, source, target, *args, **kwargs):
        self.source = source
        self.target = target
        super(BackendTransformConferenceDateTimeForm, self).__init__(*args, **kwargs)
        self.fields['timeshift'].initial = self.source.startdate - self.target.startdate

    def confirm_value(self):
        return str(self.cleaned_data['timeshift'])


class BackendConferenceSessionForm(BackendForm):
    helplink = 'schedule#sessions'
    list_fields = ['title', 'speaker_list', 'status_string', 'starttime', 'track', 'room']
    verbose_field_names = {
        'speaker_list': 'Speakers',
        'status_string': 'Status',
    }
    selectize_multiple_fields = {
        'speaker': SpeakerLookup(),
    }
    markdown_fields = ['abstract', ]
    allow_copy_previous = True
    copy_transform_form = BackendTransformConferenceDateTimeForm
    auto_cascade_delete_to = ['conferencesession_speaker', 'conferencesessionvote']
    allow_email = True

    class Meta:
        model = ConferenceSession
        fields = ['title', 'htmlicon', 'speaker', 'status', 'starttime', 'endtime', 'cross_schedule',
                  'track', 'room', 'can_feedback', 'skill_level', 'abstract', 'submissionnote']

    def fix_fields(self):
        self.fields['track'].queryset = Track.objects.filter(conference=self.conference)
        self.fields['room'].queryset = Room.objects.filter(conference=self.conference)

        if self.instance.status != self.instance.lastnotifiedstatus and self.instance.speaker.exists():
            self.fields['status'].help_text = '<b>Warning!</b> This session has <a href="/events/admin/{0}/sessionnotifyqueue/">pending notifications</a> that have not been sent. You probably want to make sure those are sent before editing the status!'.format(self.conference.urlname)

        if not self.conference.skill_levels:
            self.remove_field('skill_level')
            self.update_protected_fields()

    @classmethod
    def get_column_filters(cls, conference):
        return {
            'Status': [v for k, v in STATUS_CHOICES],
            'Track': Track.objects.filter(conference=conference),
            'Room': Room.objects.filter(conference=conference),
        }

    @classmethod
    def get_assignable_columns(cls, conference):
        return [
            {
                'name': 'track',
                'title': 'Track',
                'options': [(t.id, t.trackname) for t in Track.objects.filter(conference=conference)],
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
                ", ".join(["{0} ({1})".format(get_status_string(s), v) for s, v in valid_status_transitions[self.instance.status].items()]),
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
                                      initialsubmit=source.initialsubmit,
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
    defaultsort = [[2, 'asc']]

    def clean(self):
        cleaned_data = super(BackendFeedbackQuestionForm, self).clean()
        if not self.cleaned_data.get('isfreetext', 'False'):
            if self.cleaned_data.get('textchoices', ''):
                self.add_error('textchoices', 'Textchoices can only be specified for freetext fields')
        return cleaned_data

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
            return [(r.id, r.fullname, r.invoice_status) for r in ConferenceRegistration.objects.filter(conference=instance.conference, vouchercode=instance.code)]
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
    list_fields = ['code', 'validuntil', 'maxuses']
    linked_objects = OrderedDict({
        '../../regdashboard/list': DiscountCodeUserManager(),
    })

    form_before_new = BackendNewDiscountCodeForm

    exclude_date_validators = ['validuntil', ]

    class Meta:
        model = DiscountCode
        fields = ['code', 'discountamount', 'discountpercentage', 'regonly', 'validuntil', 'maxuses',
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
    markdown_fields = ['summary', ]
    exclude_date_validators = ['datetime', ]
    defaultsort = [[1, "desc"]]

    class Meta:
        model = ConferenceNews
        fields = ['author', 'datetime', 'title', 'inrss', 'summary', ]

    def fix_fields(self):
        # Must be administrator on current conference
        self.fields['author'].queryset = NewsPosterProfile.objects.filter(author__conference=self.conference)
        # Add help hint dynamically so we can include the conference name
        self.fields['title'].help_text = u'Note! Title will be prefixed with "{0} - " on shared frontpage and RSS!'.format(self.conference.conferencename)


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
class TwitterForm(ConcurrentProtectedModelForm):
    class Meta:
        model = Conference
        fields = ['twittersync_active', 'twitterreminders_active']


class TwitterTestForm(django.forms.Form):
    recipient = django.forms.CharField(max_length=64)
    message = django.forms.CharField(max_length=200)


#
# Form for sending email
#
class StaticWidget(django.forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        return value


class BackendSendEmailForm(django.forms.Form):
    _from = django.forms.CharField(max_length=128, disabled=True, label="Form")
    subject = django.forms.CharField(max_length=128, required=True)
    recipients = django.forms.Field(widget=StaticWidget, required=False)
    storeonregpage = django.forms.BooleanField(label="Store on registration page", required=False,
                                               help_text="If checked, store in db and show to attendees later. If not checked, one-off email is sent.")
    message = django.forms.CharField(widget=django.forms.Textarea, required=True)
    idlist = django.forms.CharField(widget=django.forms.HiddenInput, required=True)
    confirm = django.forms.BooleanField(label="Confirm", required=False)

    def __init__(self, *args, **kwargs):
        super(BackendSendEmailForm, self).__init__(*args, **kwargs)
        if not (self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")
