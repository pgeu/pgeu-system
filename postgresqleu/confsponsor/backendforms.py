from django.forms import ValidationError
import django.forms
from django.conf import settings

from collections import OrderedDict
import json

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.backendforms import BackendForm, BackendBeforeNewForm
from postgresqleu.util.backendlookups import GeneralAccountLookup
from postgresqleu.confreg.jinjafunc import JinjaTemplateValidator, render_sandboxed_template

from .models import Sponsor
from .models import SponsorshipLevel, SponsorshipContract, SponsorshipBenefit
from .models import ShipmentAddress

from .benefits import get_benefit_class, benefit_choices
from .benefitclasses import all_benefits


class BackendSponsorForm(BackendForm):
    helplink = 'sponsors#sponsor'
    fieldsets = [
        {'id': 'base_info', 'legend': 'Basic information', 'fields': ['name', 'displayname', 'url', 'twittername']},
        {'id': 'financial', 'legend': 'Financial information', 'fields': ['invoiceaddr', 'vatstatus', 'vatnumber']},
        {'id': 'management', 'legend': 'Management', 'fields': ['extra_cc', 'managers']},
        {'id': 'contract', 'legend': 'Contract', 'fields': ['autoapprovesigned', ]},
    ]
    selectize_multiple_fields = {
        'managers': GeneralAccountLookup(),
    }

    auto_cascade_delete_to = ['sponsor_managers', ]

    class Meta:
        model = Sponsor
        fields = ['name', 'displayname', 'url', 'twittername',
                  'invoiceaddr', 'vatstatus', 'vatnumber',
                  'extra_cc', 'managers', 'autoapprovesigned', ]

    def fix_fields(self):
        if not self.instance.conference.contractprovider or not self.instance.conference.autocontracts:
            del self.fields['autoapprovesigned']
            # For now remove the whole fieldset as there is only one field in it
            self.fieldsets = [fs for fs in self.fieldsets if fs['id'] != 'contract']
            self.update_protected_fields()


class BackendSponsorshipNewBenefitForm(BackendBeforeNewForm):
    helplink = 'sponsors#benefit'
    benefitclass = django.forms.ChoiceField(choices=benefit_choices)

    def get_newform_data(self):
        return self.cleaned_data['benefitclass']


class BackendSponsorshipLevelBenefitForm(BackendForm):
    helplink = 'sponsors#benefit'
    markdown_fields = ['benefitdescription', 'claimprompt', ]
    dynamic_preview_fields = ['tweet_template']
    form_before_new = BackendSponsorshipNewBenefitForm
    readonly_fields = ['benefit_class_name', ]

    class_param_fields = []  # Overridden in subclass!

    benefit_class_name = django.forms.CharField(required=False)

    @property
    def fieldsets(self):
        basefields = ['benefitname', 'benefit_class_name', 'benefitdescription', 'sortkey', 'claimprompt']
        if self.can_autoconfirm:
            basefields.append('autoconfirm')

        return [
            {'id': 'base', 'legend': 'Base', 'fields': basefields},
            {'id': 'marketing', 'legend': 'Marketing', 'fields': ['tweet_template', ]},
            {'id': 'params', 'legend': 'Parameters', 'fields': self.class_param_fields},
        ]

    @property
    def json_form_fields(self):
        return {
            'class_parameters': self.class_param_fields,
        }

    class Meta:
        model = SponsorshipBenefit
        fields = ['benefitname', 'benefitdescription', 'sortkey',
                  'claimprompt', 'tweet_template', 'benefit_class_name', 'autoconfirm']

    _can_autoconfirm = None

    @property
    def can_autoconfirm(self):
        if self._can_autoconfirm is None:
            self._can_autoconfirm = get_benefit_class(self.instance.benefit_class).can_autoconfirm
        return self._can_autoconfirm

    def fix_fields(self):
        if self.newformdata:
            if int(self.newformdata) != 0:
                self.instance.benefit_class = int(self.newformdata)
            else:
                self.instance_benefit_class = None

        self.initial['benefit_class_name'] = self.instance.benefit_class and all_benefits[self.instance.benefit_class]['description'] or ''

        self.fields['tweet_template'].validators = [
            JinjaTemplateValidator({
                'conference': self.conference,
                'benefit': self.instance,
                'level': self.instance.level,
                'sponsor': Sponsor(name='TestName', displayname="TestDisplayName", twittername="@twittertest"),
            }),
        ]

        if not self.can_autoconfirm:
            del self.fields['autoconfirm']
            self.update_protected_fields()

    @classmethod
    def get_dynamic_preview(self, fieldname, s, objid):
        if fieldname == 'tweet_template':
            if objid:
                o = self.Meta.model.objects.get(pk=objid)
                return render_sandboxed_template(s, {
                    'benefit': o,
                    'level': o.level,
                    'conference': o.level.conference,
                    'sponsor': Sponsor(name='TestName', displayname="TestDisplayName", twittername="@twittertest"),
                })
            return ''


class BackendSponsorshipLevelBenefitManager(object):
    title = 'Benefits'
    singular = 'benefit'
    can_add = True
    fieldset = {
        'id': 'benefits',
        'legend': 'Benefits',
    }

    def get_list(self, instance):
        return [(b.id, b.benefitname, b.benefitdescription) for b in instance.sponsorshipbenefit_set.all()]

    def get_form(self, obj, POST):
        if obj and obj.benefit_class:
            return get_benefit_class(obj.benefit_class).get_backend_form()
        elif POST.get('_newformdata'):
            bc = get_benefit_class(int(POST.get('_newformdata')))
            if bc:
                return bc.get_backend_form()
        elif POST.get('benefitclass', None):
            bc = get_benefit_class(int(POST.get('benefitclass')))
            if bc:
                return bc.get_backend_form()
        return BackendSponsorshipLevelBenefitForm

    def get_object(self, masterobj, subjid):
        try:
            return SponsorshipBenefit.objects.get(level=masterobj, pk=subjid)
        except SponsorshipBenefit.DoesNotExist:
            return None

    def get_instancemaker(self, masterobj):
        return lambda: SponsorshipBenefit(level=masterobj, class_parameters={})


class BackendSponsorshipLevelForm(BackendForm):
    helplink = 'sponsors#level'
    list_fields = ['levelname', 'levelcost', 'available', 'public', ]
    linked_objects = OrderedDict({
        'benefit': BackendSponsorshipLevelBenefitManager(),
    })
    allow_copy_previous = True
    auto_cascade_delete_to = ['sponsorshiplevel_paymentmethods', 'sponsorshipbenefit']

    class Meta:
        model = SponsorshipLevel
        fields = ['levelname', 'urlname', 'levelcost', 'available', 'public', 'maxnumber', 'instantbuy',
                  'paymentmethods', 'invoiceextradescription', 'contract', 'canbuyvoucher', 'canbuydiscountcode']
        widgets = {
            'paymentmethods': django.forms.CheckboxSelectMultiple,
        }

    fieldsets = [
        {
            'id': 'base_info',
            'legend': 'Basic information',
            'fields': ['levelname', 'urlname', 'levelcost', 'available', 'public', 'maxnumber', ]
        },
        {
            'id': 'contract',
            'legend': 'Contract information',
            'fields': ['instantbuy', 'contract', ],
        },
        {
            'id': 'payment',
            'legend': 'Payment information',
            'fields': ['paymentmethods', 'invoiceextradescription', ],
        },
        {
            'id': 'services',
            'legend': 'Services',
            'fields': ['canbuyvoucher', 'canbuydiscountcode', ],
        },
    ]

    def fix_fields(self):
        self.fields['contract'].queryset = SponsorshipContract.objects.filter(conference=self.conference)
        self.fields['paymentmethods'].label_from_instance = lambda x: "{0}{1}".format(x.internaldescription, x.active and " " or " (INACTIVE)")

    def clean(self):
        cleaned_data = super(BackendSponsorshipLevelForm, self).clean()

        if not (cleaned_data.get('instantbuy', False) or cleaned_data['contract']):
            self.add_error('instantbuy', 'Sponsorship level must either be instant signup or have a contract')
            self.add_error('contract', 'Sponsorship level must either be instant signup or have a contract')

        if int(cleaned_data['levelcost'] == 0) and cleaned_data.get('instantbuy', False):
            self.add_error('levelcost', 'Sponsorships with zero cost can not be instant signup')
            self.add_error('instantbuy', 'Sponsorships with zero cost can not be instant signup')

        return cleaned_data

    def clean_urlname(self):
        val = self.cleaned_data['urlname']
        if val and SponsorshipLevel.objects.filter(conference=self.conference, urlname=val).exclude(pk=self.instance.pk).exists():
            raise ValidationError("A sponsorship level with this URL name already exists")
        return val

    @classmethod
    def copy_from_conference(self, targetconf, sourceconf, idlist):
        for id in idlist:
            level = SponsorshipLevel.objects.get(pk=id, conference=sourceconf)
            if SponsorshipLevel.objects.filter(conference=targetconf, urlname=level.urlname).exists():
                yield 'A sponsorship level with urlname {0} already exists.'.format(level.urlname)
                continue

            # Get a separate instance that we will modify
            newlevel = SponsorshipLevel.objects.get(pk=id, conference=sourceconf)
            # Set pk to None to make a copy
            newlevel.pk = None
            newlevel.conference = targetconf
            newlevel.contract = None
            newlevel.save()
            for pm in level.paymentmethods.all():
                newlevel.paymentmethods.add(pm)
            newlevel.save()
            for b in level.sponsorshipbenefit_set.all():
                b.pk = None
                b.level = newlevel
                if b.benefit_class is not None:
                    c = get_benefit_class(b.benefit_class)(b.level, b.class_parameters)
                    try:
                        c.validate_parameters()
                    except ValidationError as e:
                        yield 'Cannot copy level {}, benefit {} cannot be copied: {}'.format(level.levelname, b.benefitname, e.message)
                        continue
                b.save()


class BackendSponsorshipContractForm(BackendForm):
    helplink = 'sponsors#contract'
    list_fields = ['contractname', ]
    exclude_fields_from_validation = ['contractpdf', ]

    class Meta:
        model = SponsorshipContract
        fields = ['contractname', 'contractpdf', ]

    @property
    def extrabuttons(self):
        yield ('Edit field locations', 'editfields/')
        yield ('Preview with fields', 'previewfields/')
        if self.conference.contractprovider:
            yield ('Edit digital signage fields', 'editdigifields/')
            if self.conference.contractprovider.get_implementation().can_send_preview:
                yield ('Send test contract', 'sendtest/')
        yield ('Copy fields from another contract', 'copyfields/')

    def fix_fields(self):
        # Field must be non-required so we can save things. The widget is still required,
        # so things cannot be removed. Yes, that's kind of funky.
        if self.instance.pk:
            self.fields['contractpdf'].required = False


class BackendShipmentAddressForm(BackendForm):
    helplink = 'sponsors#shpiment'
    list_fields = ['title', 'active', 'startdate', 'enddate', ]
    exclude_date_validators = ['startdate', 'enddate']
    markdown_fields = ['description', ]
    readonly_fields = ['receiverlink', ]

    receiverlink = django.forms.CharField(required=False, label="Recipient link", widget=StaticTextWidget)

    class Meta:
        model = ShipmentAddress
        fields = ['title', 'active', 'startdate', 'enddate', 'available_to', 'address', 'description', ]

    def fix_fields(self):
        self.fields['available_to'].queryset = SponsorshipLevel.objects.filter(conference=self.conference)
        self.fields['address'].help_text = "Full address. %% will be substituted with the unique address number, so don't forget to include it!"
        self.initial['receiverlink'] = 'The recipient should use the link <a href="{0}/events/sponsor/shipments/{1}/">{0}/events/sponsor/shipments/{1}/</a> to access the system.'.format(settings.SITEBASE, self.instance.token)


class BackendSponsorshipSendTestForm(django.forms.Form):
    recipientname = django.forms.CharField(max_length=100, label='Recipient name')
    recipientemail = django.forms.EmailField(max_length=100, label='Recipient email')

    def __init__(self, contract, user, *args, **kwargs):
        self.contract = contract
        self.user = user
        super().__init__(*args, **kwargs)
        self.initial = {
            'recipientname': '{} {}'.format(user.first_name, user.last_name),
            'recipientemail': user.email,
        }


class BackendCopyContractFieldsForm(django.forms.Form):
    currentval = django.forms.CharField(required=False, label="Current fields", widget=StaticTextWidget(monospace=True),
                                        help_text="NOTE! This value will be completely overwritten!")
    copyfrom = django.forms.ChoiceField(choices=[], label="Copy from contract")

    def __init__(self, contract, *args, **kwargs):
        self.contract = contract
        super().__init__(*args, **kwargs)
        self.fields['copyfrom'].choices = [(c.id, c.contractname) for c in SponsorshipContract.objects.filter(conference=contract.conference).exclude(pk=contract.pk).order_by('contractname')]

        if not contract.fieldjson:
            del self.fields['currentval']
        else:
            self.initial['currentval'] = json.dumps(contract.fieldjson, indent=2)
