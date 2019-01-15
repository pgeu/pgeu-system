from django.forms import ValidationError
import django.forms

from collections import OrderedDict

from postgresqleu.util.magic import magicdb
from postgresqleu.util.widgets import RequiredFileUploadWidget
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.util.backendlookups import GeneralAccountLookup
from postgresqleu.confreg.jinjafunc import JinjaTemplateValidator, render_sandboxed_template

from .models import Sponsor
from .models import SponsorshipLevel, SponsorshipContract, SponsorshipBenefit

from .benefits import get_benefit_class, benefit_choices
from .benefitclasses import all_benefits


class BackendSponsorForm(BackendForm):
    helplink = 'sponsors#sponsor'
    fieldsets = [
        {'id': 'base_info', 'legend': 'Basic information', 'fields': ['name', 'displayname', 'url', 'twittername']},
        {'id': 'financial', 'legend': 'Financial information', 'fields': ['invoiceaddr', 'vatstatus', 'vatnumber']},
        {'id': 'management', 'legend': 'Management', 'fields': ['extra_cc', 'managers']},
    ]
    selectize_multiple_fields = {
        'managers': GeneralAccountLookup(),
    }

    auto_cascade_delete_to = ['sponsor_managers', ]

    class Meta:
        model = Sponsor
        fields = ['name', 'displayname', 'url', 'twittername',
                  'invoiceaddr', 'vatstatus', 'vatnumber',
                  'extra_cc', 'managers', ]


class BackendSponsorshipNewBenefitForm(django.forms.Form):
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

    benefit_class_name = django.forms.CharField()

    @property
    def fieldsets(self):
        return [
            {'id': 'base', 'legend': 'Base', 'fields': ['benefitname', 'benefit_class_name', 'benefitdescription', 'sortkey', 'claimprompt']},
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
                  'claimprompt', 'tweet_template', 'benefit_class_name']

    def fix_fields(self):
        if self.newformdata:
            self.instance.benefit_class = int(self.newformdata)
        self.initial['benefit_class_name'] = self.instance.benefit_class and all_benefits[self.instance.benefit_class]['description'] or ''

        self.fields['tweet_template'].validators = [
            JinjaTemplateValidator({
                'conference': self.conference,
                'benefit': self.instance,
                'level': self.instance.level,
                'sponsor': Sponsor(name='Test'),
            }),
        ]

    @classmethod
    def get_dynamic_preview(self, fieldname, s, objid):
        if fieldname == 'tweet_template':
            if objid:
                o = self.Meta.model.objects.get(pk=objid)
                return render_sandboxed_template(s, {
                    'benefit': o,
                    'level': o.level,
                    'conference': o.level.conference,
                    'sponsor': Sponsor(name='Test'),
                })
            return ''


class BackendSponsorshipLevelBenefitManager(object):
    title = 'Benefits'
    singular = 'benefit'
    can_add = True

    def get_list(self, instance):
        return [(b.id, b.benefitname, b.benefitdescription) for b in instance.sponsorshipbenefit_set.all()]

    def get_form(self, obj, POST):
        if obj and obj.benefit_class:
            return get_benefit_class(obj.benefit_class).get_backend_form()
        elif POST.get('_newformdata'):
            return get_benefit_class(int(POST.get('_newformdata'))).get_backend_form()
        elif POST.get('benefitclass', None):
            return get_benefit_class(int(POST.get('benefitclass'))).get_backend_form()
        else:
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
    list_fields = ['levelname', 'levelcost', 'available', ]
    linked_objects = OrderedDict({
        'benefit': BackendSponsorshipLevelBenefitManager(),
    })
    allow_copy_previous = True
    auto_cascade_delete_to = ['sponsorshiplevel_paymentmethods', 'sponsorshipbenefit']

    class Meta:
        model = SponsorshipLevel
        fields = ['levelname', 'urlname', 'levelcost', 'available', 'maxnumber', 'instantbuy',
                  'paymentmethods', 'contract', 'canbuyvoucher', 'canbuydiscountcode']

    def fix_fields(self):
        self.fields['contract'].queryset = SponsorshipContract.objects.filter(conference=self.conference)
        self.fields['paymentmethods'].label_from_instance = lambda x: x.internaldescription

    def clean(self):
        cleaned_data = super(BackendSponsorshipLevelForm, self).clean()

        if not (cleaned_data.get('instantbuy', False) or cleaned_data['contract']):
            self.add_error('instantbuy', 'Sponsorship level must either be instant signup or have a contract')
            self.add_error('contract', 'Sponsorship level must either be instant signup or have a contract')

        return cleaned_data

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
                b.save()


class BackendSponsorshipContractForm(BackendForm):
    helplink = 'sponsors#contract'
    list_fields = ['contractname', ]
    file_fields = ['contractpdf', ]

    class Meta:
        model = SponsorshipContract
        fields = ['contractname', 'contractpdf', ]

    def fix_fields(self):
        self.fields['contractpdf'].widget = RequiredFileUploadWidget(filename='{0}.pdf'.format(self.instance.contractname))

    def validate_file(self, field, f):
        if field == 'contractpdf':
            if not f:
                if getattr(self.instance, 'contractpdf', None):
                    # No file included in this upload, but it existed before. So
                    # just leave untouched.
                    return None
                return "Contract must be uploaded"
            mtype = magicdb.buffer(f.read())
            if not mtype.startswith('application/pdf'):
                return "Contracts must be uploaded in PDF format, not %s" % mtype
            f.seek(0)
