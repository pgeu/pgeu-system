from django.forms import ValidationError

from collections import OrderedDict

from postgresqleu.util.magic import magicdb
from postgresqleu.util.widgets import RequiredFileUploadWidget, PrettyPrintJsonWidget
from postgresqleu.confreg.backendforms import BackendForm
from postgresqleu.confreg.backendlookups import GeneralAccountLookup

from models import Sponsor
from models import SponsorshipLevel, SponsorshipContract, SponsorshipBenefit

from benefits import get_benefit_class
from benefitclasses import all_benefits

import json

class BackendSponsorForm(BackendForm):
	helplink='sponsors#sponsor'
	class Meta:
		model = Sponsor
		fields = ['name', 'displayname', 'url', 'twittername',
				  'invoiceaddr', 'vatstatus', 'vatnumber',
				  'managers', ]
	fieldsets = [
		{'id': 'base_info', 'legend': 'Basic information', 'fields': ['name', 'displayname', 'url', 'twittername']},
		{'id': 'financial', 'legend': 'Financial information', 'fields': ['invoiceaddr', 'vatstatus', 'vatnumber']},
		{'id': 'management', 'legend': 'Management', 'fields': ['managers']},
	]

	selectize_multiple_fields = {
		'managers': GeneralAccountLookup(),
	}

	auto_cascade_delete_to = ['sponsor_managers', ]


class BackendSponsorshipLevelBenefitForm(BackendForm):
	helplink='sponsors#benefit'
	json_fields = ['class_parameters', ]
	class Meta:
		model = SponsorshipBenefit
		fields = ['benefitname', 'benefitdescription', 'sortkey', 'benefit_class',
				  'claimprompt', 'class_parameters', ]
		widgets = {
			'class_parameters': PrettyPrintJsonWidget,
		}

	def clean(self):
		cleaned_data = super(BackendSponsorshipLevelBenefitForm, self).clean()
		if cleaned_data.get('benefit_class') >= 0:
			params = cleaned_data.get('class_parameters')
			benefit = get_benefit_class(cleaned_data.get('benefit_class'))(self.instance.level, params)
			if not params:
				# Need a copy of the local data to make it mutable and change our default
				self.data = self.data.copy()
				if benefit.default_params:
					dp = benefit.default_params
				else:
					dp = {}
				self.data['class_parameters'] = json.dumps(dp)
				self.instance.class_parameters = dp
				cleaned_data['class_parameters'] = dp
				benefit.params = dp
			try:
				benefit.do_validate_params()
			except ValidationError, e:
				self.add_error('class_parameters', e)
		return cleaned_data

	@property
	def json_merge_data(self):
		return json.dumps([{
			'source': 'id_benefit_class',
			'target': 'id_class_parameters',
			'map': {k:v['class'].default_params for k,v in all_benefits.items()}
		}])

class BackendSponsorshipLevelBenefitManager(object):
	title = 'Benefits'
	singular = 'benefit'
	can_add = True

	def get_list(self, instance):
		return [(b.id, b.benefitname, b.benefitdescription) for b in instance.sponsorshipbenefit_set.all()]

	def get_form(self):
		return BackendSponsorshipLevelBenefitForm

	def get_object(self, masterobj, subjid):
		try:
			return SponsorshipBenefit.objects.get(level=masterobj, pk=subjid)
		except SponsorshipBenefit.DoesNotExist:
			return None

	def get_instancemaker(self, masterobj):
		return lambda: SponsorshipBenefit(level=masterobj)

class BackendSponsorshipLevelForm(BackendForm):
	helplink='sponsors#level'
	list_fields = ['levelname', 'levelcost', 'available', ]
	linked_objects = OrderedDict({
		'benefit': BackendSponsorshipLevelBenefitManager(),
	})
	allow_copy_previous = True
	auto_cascade_delete_to = ['sponsorshiplevel_paymentmethods', 'sponsorshipbenefit']

	class Meta:
		model = SponsorshipLevel
		fields = ['levelname', 'urlname', 'levelcost', 'available', 'instantbuy',
				  'paymentmethods', 'contract', 'canbuyvoucher', 'canbuydiscountcode']

	def fix_fields(self):
		self.fields['contract'].queryset = SponsorshipContract.objects.filter(conference=self.conference)
		self.fields['paymentmethods'].label_from_instance = lambda x: x.internaldescription


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
	helplink='sponsors#contract'
	list_fields = ['contractname', ]
	file_fields = ['contractpdf', ]
	class Meta:
		model = SponsorshipContract
		fields = ['contractname', 'contractpdf' ]

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
