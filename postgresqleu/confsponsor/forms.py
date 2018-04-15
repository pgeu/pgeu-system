from django import forms
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.db.models import Q
from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings

from models import Sponsor, SponsorMail, SponsorshipLevel
from models import vat_status_choices
from postgresqleu.confreg.models import Conference, RegistrationType, DiscountCode
from postgresqleu.countries.models import EuropeCountry

from postgresqleu.confreg.models import ConferenceAdditionalOption
from postgresqleu.util.validators import BeforeValidator, AfterValidator, TwitterValidator

from datetime import date, timedelta

def _int_with_default(s, default):
	try:
		return int(s)
	except ValueError:
		return default
	except TypeError:
		return default

class SponsorSignupForm(forms.Form):
	name = forms.CharField(label="Company name *", min_length=3, max_length=100, help_text="This name is used on invoices and in internal communication")
	displayname = forms.CharField(label="Display name *", min_length=3, max_length=100, help_text="This name is displayed on websites and in public communication")
	address = forms.CharField(label="Company invoice address *", min_length=10, max_length=500, widget=forms.Textarea)
	vatstatus = forms.ChoiceField(label="Company VAT status", choices=vat_status_choices)
	vatnumber = forms.CharField(label="EU VAT Number", min_length=5, max_length=50, help_text="Enter EU VAT Number to be included on invoices if assigned one. Leave empty if outside the EU or without assigned VAT number.", required=False)
	url = forms.CharField(label="Company URL *", min_length=8, max_length=100)
	twittername = forms.CharField(label="Company twitter", min_length=0, max_length=100, required=False, validators=[TwitterValidator, ])
	confirm = forms.BooleanField(help_text="Check this box to that you have read and agree to the terms in the contract")

	def __init__(self, conference, *args, **kwargs):
		self.conference = conference

		super(SponsorSignupForm, self).__init__(*args, **kwargs)

		if not self.conference.twitter_sponsorlist:
			del self.fields['twittername']

		if not settings.EU_VAT:
			del self.fields['vatstatus']
			del self.fields['vatnumber']

	def clean_name(self):
		if Sponsor.objects.filter(conference=self.conference, name__iexact=self.cleaned_data['name']).exists():
			raise ValidationError("A sponsor with this name is already signed up for this conference!")
		return self.cleaned_data['name']

	def clean_displayname(self):
		if Sponsor.objects.filter(conference=self.conference, displayname__iexact=self.cleaned_data['displayname']).exists():
			raise ValidationError("A sponsor with this display name is already signed up for this conference!")
		return self.cleaned_data['displayname']

	def clean_vatnumber(self):
		# EU VAT numbers begin with a two letter country-code, so let's
		# validate that first
		v = self.cleaned_data['vatnumber'].upper()

		if v == "":
			# We allow empty VAT numbers, for sponsors from outside of
			# europe.
			return v

		if not EuropeCountry.objects.filter(iso=v[:2]).exists():
			raise ValidationError("VAT numbers must begin with the two letter country code")
		if settings.EU_VAT_VALIDATE:
			import vatutil
			r = vatutil.validate_eu_vat_number(v)
			if r:
				raise ValidationError("Invalid VAT number: %s" % r)
		return v

	def clean(self):
		cleaned_data = super(SponsorSignupForm, self).clean()
		if settings.EU_VAT:
			if int(cleaned_data['vatstatus']) == 0:
				# Company inside EU and has VAT number
				if not cleaned_data.get('vatnumber', None):
					self.add_error('vatnumber', 'VAT number must be specified for companies inside EU with VAT number')
			elif int(cleaned_data['vatstatus']) == 1:
				# Company inside EU but without VAT number
				if cleaned_data.get('vatnumber', None):
					self.add_error('vatnumber', 'VAT number should not be specified for companies without one!')
			else:
				# Company outside EU
				if cleaned_data.get('vatnumber', None):
					self.add_error('vatnumber', 'VAT number should not be specified for companies outside EU')

		return cleaned_data

class SponsorSendEmailForm(forms.ModelForm):
	confirm = forms.BooleanField(label="Confirm", required=False)
	class Meta:
		model = SponsorMail
		exclude = ('conference', )

	def __init__(self, conference, *args, **kwargs):
		self.conference = conference
		super(SponsorSendEmailForm, self).__init__(*args, **kwargs)
		self.fields['levels'].widget = forms.CheckboxSelectMultiple()
		self.fields['levels'].queryset = SponsorshipLevel.objects.filter(conference=self.conference)

		if not (self.data.get('levels') and self.data.get('subject') and self.data.get('message')):
				del self.fields['confirm']

	def clean_confirm(self):
		if not self.cleaned_data['confirm']:
			raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")

class PurchaseVouchersForm(forms.Form):
	regtype = forms.ModelChoiceField(queryset=None, required=True, label="Registration type")
	num = forms.IntegerField(required=True, initial=2,
							 label="Number of vouchers",
							 validators=[MinValueValidator(1), ])
	confirm = forms.BooleanField(help_text="Check this form to confirm that you will pay the generated invoice")

	def __init__(self, conference, *args, **kwargs):
		self.conference = conference
		super(PurchaseVouchersForm, self).__init__(*args, **kwargs)
		activeQ = Q(activeuntil__isnull=True) | Q(activeuntil__gt=date.today())
		if self.data and self.data.has_key('regtype') and self.data['regtype'] and self.data.has_key('num') and self.data['num'] and _int_with_default(self.data['num'], 0) > 0:
			rt = RegistrationType.objects.get(pk=self.data['regtype'])
			self.fields['confirm'].help_text = 'Check this box to confirm that you will pay the generated invoice'
			self.fields['num'].widget.attrs['readonly'] = True
			self.fields['regtype'].queryset = RegistrationType.objects.filter(pk=self.data['regtype'])
		else:
			self.fields['regtype'].queryset = RegistrationType.objects.filter(Q(conference=self.conference, active=True, specialtype__isnull=True, cost__gt=0) & activeQ)
			del self.fields['confirm']

class PurchaseDiscountForm(forms.Form):
	code = forms.CharField(required=True, max_length=100, min_length=4,
						   help_text='Enter the code you want to use to provide the discount.')
	amount = forms.IntegerField(required=False, initial=0,
								label="Fixed discount in {0}".format(settings.CURRENCY_ABBREV),
								validators=[MinValueValidator(0), ])
	percent = forms.IntegerField(required=False, initial=0,
								 label="Percent discount",
								 validators=[MinValueValidator(0), MaxValueValidator(100), ])
	maxuses = forms.IntegerField(required=True, initial=1,
								 label="Maximum uses",
								 validators=[MinValueValidator(1), MaxValueValidator(30), ])
	expires = forms.DateField(required=True, label="Expiry date")
	requiredoptions = forms.ModelMultipleChoiceField(required=False, queryset=None, label="Required options",
													 widget=forms.CheckboxSelectMultiple,
													 help_text="Check any additional options that are required. Registrations without those options will not be able to use the discount code.")
	confirm = forms.BooleanField(help_text="Check this form to confirm that you will pay the costs generated by the people using this code, as specified by the invoice.")

	def __init__(self, conference, showconfirm=False, *args, **kwargs):
		self.conference = conference
		super(PurchaseDiscountForm, self).__init__(*args, **kwargs)
		self.fields['requiredoptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=conference)
		self.fields['expires'].initial=conference.startdate-timedelta(days=2)
		self.fields['expires'].validators.append(BeforeValidator(conference.startdate-timedelta(days=1)))
		self.fields['expires'].validators.append(AfterValidator(date.today()-timedelta(days=1)))
		if not showconfirm:
			del self.fields['confirm']

	def clean_code(self):
		# Check if code is already in use for this conference
		if DiscountCode.objects.filter(conference=self.conference, code=self.cleaned_data['code'].upper()).exists():
			raise ValidationError("This discount code is already in use for this conference")

		# Force to uppercase. CSS takes care of that at the presentation layer
		return self.cleaned_data['code'].upper()

	def clean(self):
		cleaned_data = super(PurchaseDiscountForm, self).clean()

		if cleaned_data.has_key('amount') and cleaned_data.has_key('percent'):
			# Only one can be specified
			if _int_with_default(cleaned_data['amount'], 0) > 0 and _int_with_default(cleaned_data['percent'], 0) > 0:
				self._errors['amount'] = ErrorList(['Cannot specify both amount and percent!'])
				self._errors['percent'] = ErrorList(['Cannot specify both amount and percent!'])
			elif _int_with_default(cleaned_data['amount'], 0) == 0 and _int_with_default(cleaned_data['percent'], 0) == 0:
				self._errors['amount'] = ErrorList(['Must specify amount or percent!'])
				self._errors['percent'] = ErrorList(['Must specify amount or percent!'])

		return cleaned_data


class AdminCopySponsorshipLevelForm(forms.Form):
	targetconference = forms.ModelChoiceField(queryset=Conference.objects.all(), label='Target conference')
