from django.forms import ValidationError

from collections import OrderedDict

from postgresqleu.util.magic import magicdb
from postgresqleu.util.widgets import RequiredFileUploadWidget
from postgresqleu.confreg.backendforms import BackendForm

from models import SponsorshipLevel, SponsorshipContract, SponsorshipBenefit

from benefits import get_benefit_class

class BackendSponsorshipLevelBenefitForm(BackendForm):
	json_fields = ['class_parameters', ]
	class Meta:
		model = SponsorshipBenefit
		fields = ['benefitname', 'benefitdescription', 'sortkey', 'benefit_class',
				  'claimprompt', 'class_parameters', ]

	def clean(self):
		cleaned_data = super(BackendSponsorshipLevelBenefitForm, self).clean()
		if cleaned_data.get('benefit_class') >= 0:
			params = cleaned_data.get('class_parameters')
			benefit = get_benefit_class(cleaned_data.get('benefit_class'))(self.instance, params)
			if params == "" and benefit.default_params:
				cleaned_data['class_parameters'] = benefit.default_params
				self.instance.class_parameters = benefit.default_params
				params = benefit.default_params
			s = benefit.validate_params()
			if s:
				self.add_error('class_parameters', s)

		return cleaned_data


class BackendSponsorshipLevelBenefitManager(object):
	title = 'Benefits'
	singular = 'benefit'

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
	list_fields = ['levelname', 'levelcost', 'available', ]
	linked_objects = OrderedDict({
		'benefit': BackendSponsorshipLevelBenefitManager(),
	})
	class Meta:
		model = SponsorshipLevel
		fields = ['levelname', 'urlname', 'levelcost', 'available', 'instantbuy',
				  'paymentmethods', 'contract', 'canbuyvoucher', 'canbuydiscountcode']

	def fix_fields(self):
		self.fields['contract'].queryset = SponsorshipContract.objects.filter(conference=self.conference)
		self.fields['paymentmethods'].label_from_instance = lambda x: x.internaldescription


class BackendSponsorshipContractForm(BackendForm):
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
