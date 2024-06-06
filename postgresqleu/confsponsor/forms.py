from django import forms
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.db.models import Q
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User
from django.conf import settings

from .models import Sponsor, SponsorMail, SponsorshipLevel, SponsorshipContract
from .models import vat_status_choices
from .models import Shipment
from postgresqleu.confreg.models import RegistrationType, DiscountCode
from postgresqleu.countries.models import EuropeCountry

from postgresqleu.confreg.models import ConferenceAdditionalOption
from postgresqleu.confreg.twitter import get_all_conference_social_media
from postgresqleu.util.fields import UserModelChoiceField
from postgresqleu.util.validators import BeforeValidator, AfterValidator
from postgresqleu.util.validators import Http200Validator
from postgresqleu.util.widgets import Bootstrap4CheckboxSelectMultiple, EmailTextWidget
from postgresqleu.util.widgets import Bootstrap4HtmlDateTimeInput
from postgresqleu.util.time import today_conference

from datetime import timedelta
from decimal import Decimal


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
    address = forms.CharField(label="Company invoice address *", min_length=10, max_length=500, widget=forms.Textarea, help_text="The sponsor name is automatically included at beginning of address. The VAT number is automatically included at end of address.")
    vatstatus = forms.ChoiceField(label="Company VAT status", choices=vat_status_choices)
    vatnumber = forms.CharField(label="EU VAT Number", min_length=5, max_length=50, help_text="Enter EU VAT Number to be included on invoices if assigned one. Leave empty if outside the EU or without assigned VAT number.", required=False)
    url = forms.URLField(label="Company URL *", validators=[Http200Validator, ])

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference

        super(SponsorSignupForm, self).__init__(*args, **kwargs)

        for classname, social, impl in sorted(get_all_conference_social_media('sponsor'), key=lambda x: x[1]):
            fn = "social_{}".format(social)
            self.fields[fn] = forms.CharField(label="Company {}".format(social.title()), max_length=250, required=False)
            if hasattr(impl, 'get_field_help'):
                self.fields[fn].help_text = impl.get_field_help('sponsor')

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
        v = self.cleaned_data['vatnumber'].upper().replace(' ', '')

        if v == "":
            # We allow empty VAT numbers, for sponsors from outside of
            # europe.
            return v

        countrycode = v[:2]
        if countrycode == 'EL':
            # Greece for some reason uses EL instead of their ISO code GR
            # (ref: https://en.wikipedia.org/wiki/VAT_identification_number#Structure)
            countrycode = 'GR'

        if not EuropeCountry.objects.filter(iso=countrycode).exists():
            raise ValidationError("VAT numbers must begin with the two letter country code")
        if settings.EU_VAT_VALIDATE:
            from . import vatutil
            r = vatutil.validate_eu_vat_number(v)
            if r:
                raise ValidationError("Invalid VAT number: %s" % r)
        return v

    def clean(self):
        cleaned_data = super(SponsorSignupForm, self).clean()

        for classname, social, impl in get_all_conference_social_media('sponsor'):
            fn = 'social_{}'.format(social)
            if cleaned_data.get(fn, None):
                try:
                    cleaned_data[fn] = impl.clean_identifier_form_value('sponsor', cleaned_data[fn])
                except ValidationError as v:
                    self.add_error(fn, v)

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
        exclude = ('conference', 'sent', )
        widgets = {
            'message': EmailTextWidget(),
        }

    def __init__(self, conference, sendto, *args, **kwargs):
        self.conference = conference
        self.sendto = sendto
        super(SponsorSendEmailForm, self).__init__(*args, **kwargs)
        if self.sendto == 'level':
            self.fields['levels'].widget = forms.CheckboxSelectMultiple()
            self.fields['levels'].queryset = SponsorshipLevel.objects.filter(conference=self.conference)
            self.fields['levels'].required = True
            del self.fields['sponsors']
        else:
            self.fields['sponsors'].widget = forms.CheckboxSelectMultiple()
            self.fields['sponsors'].queryset = Sponsor.objects.select_related('level').filter(conference=self.conference)
            self.fields['sponsors'].required = True
            self.fields['sponsors'].label_from_instance = lambda s: "{0} ({1}, {2})".format(s, s.level.levelname, s.confirmed and "confirmed {:%Y-%m-%d %H:%M}".format(s.confirmedat) or "NOT confirmed")
            del self.fields['levels']

        self.fields['subject'].help_text = 'Subject will be prefixed with <strong>[{}]</strong>'.format(conference)

        if not ((self.data.get('levels') or self.data.get('sponsors')) and self.data.get('subject') and self.data.get('message')):
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
        activeQ = Q(activeuntil__isnull=True) | Q(activeuntil__gte=today_conference())
        if self.data and self.data.get('regtype', None) and self.data.get('num', None) and _int_with_default(self.data['num'], 0) > 0:
            RegistrationType.objects.get(pk=self.data['regtype'])
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
    requiredoptions = forms.ModelMultipleChoiceField(
        required=False, queryset=None,
        label="Attendee add-ons required to use the code",
        widget=Bootstrap4CheckboxSelectMultiple,
        help_text="Check any additional options that are required. Registrations without those options will not be able to use the discount code."
    )
    confirm = forms.BooleanField(help_text="Check this form to confirm that you will pay the costs generated by the people using this code, as specified by the invoice.")

    def __init__(self, conference, showconfirm=False, *args, **kwargs):
        self.conference = conference
        super(PurchaseDiscountForm, self).__init__(*args, **kwargs)
        self.fields['requiredoptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=conference, public=True)
        self.fields['expires'].initial = conference.startdate - timedelta(days=2)
        self.fields['expires'].validators.append(BeforeValidator(conference.startdate - timedelta(days=1)))
        self.fields['expires'].validators.append(AfterValidator(today_conference() - timedelta(days=1)))
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

        if 'amount' in cleaned_data and 'percent' in cleaned_data:
            # Only one can be specified
            if _int_with_default(cleaned_data['amount'], 0) > 0 and _int_with_default(cleaned_data['percent'], 0) > 0:
                self._errors['amount'] = ErrorList(['Cannot specify both amount and percent!'])
                self._errors['percent'] = ErrorList(['Cannot specify both amount and percent!'])
            elif _int_with_default(cleaned_data['amount'], 0) == 0 and _int_with_default(cleaned_data['percent'], 0) == 0:
                self._errors['amount'] = ErrorList(['Must specify amount or percent!'])
                self._errors['percent'] = ErrorList(['Must specify amount or percent!'])

        return cleaned_data


class SponsorDetailsForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        fields = ('extra_cc', )


class SponsorRefundForm(forms.Form):
    refundamount = forms.ChoiceField(choices=(
        (0, "Refund full invoice cost"),
        (1, "Refund custom amount"),
        (2, "Don't refund"),
    ), label="Refund amount")
    customrefundamount = forms.DecimalField(decimal_places=2, required=False, label="Custom refund amount (ex VAT)")
    customrefundamountvat = forms.DecimalField(decimal_places=2, required=False, label="Custom VAT refund amount")
    cancelmethod = forms.ChoiceField(choices=(
        (0, "Cancel sponsorship"),
        (1, "Leave sponsorship active"),
    ), label="Cancel method")
    confirm = forms.BooleanField(help_text="Confirm that you want to cancel or refund this sponsorship!")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.EU_VAT:
            self.fields['customrefundamount'].label = 'Custom refund amount'
            del self.fields['customrefundamountvat']

        if 'refundamount' not in self.data or 'cancelmethod' not in self.data:
            del self.fields['confirm']

    def clean(self):
        d = super().clean()
        if int(d['refundamount']) == 1:
            # Custom amount, so make sure both those fields are set
            if d['customrefundamount'] is None:
                self.add_error('customrefundamount', 'This field is required when doing custom amount refund')
            elif Decimal(d['customrefundamount'] <= 0):
                self.add_error('customrefundamount', 'Must be >0 when performing custom refund')
            if settings.EU_VAT and d['customrefundamountvat'] is None:
                self.add_error('customrefundamountvat', 'This field is required when doing custom amount refund')
        else:
            if d['customrefundamount'] is not None:
                self.add_error('customrefundamount', 'This field must be left empty when doing non-custom refund')
            if settings.EU_VAT and d['customrefundamountvat'] is not None:
                self.add_error('customrefundamountvat', 'This field must be left empty when doing non-custom refund')

        return d


class SponsorReissueForm(forms.Form):
    confirm = forms.BooleanField(required=True, label='Confirm reissuing of invoice',
                                 help_text='New invoice will be automatically sent to the sponsor')


class SponsorShipmentForm(forms.ModelForm):
    sent_parcels = forms.ChoiceField(choices=[], required=True)

    class Meta:
        model = Shipment
        fields = ('description', 'sent_parcels', 'sent_at', 'trackingnumber', 'shippingcompany', 'trackinglink')
        widgets = {
            'sent_at': Bootstrap4HtmlDateTimeInput,
        }

    fieldsets = [
        {
            'id': 'shipment',
            'legend': 'Shipment',
            'fields': ['description', 'sent_parcels', 'sent_at', ],
        },
        {
            'id': 'tracking',
            'legend': 'Tracking',
            'fields': ['trackingnumber', 'shippingcompany', 'trackinglink', ],
        }
    ]

    def __init__(self, *args, **kwargs):
        super(SponsorShipmentForm, self).__init__(*args, **kwargs)
        self.fields['sent_at'].help_text = "Date and (approximate) time when parcels were sent. <strong>DO NOT</strong> set until shipment is actually sent"
        self.fields['sent_parcels'].choices = [('0', " * Don't know yet"), ] + [(str(x), str(x)) for x in range(1, 20)]
        self.fields['trackinglink'].validators.append(Http200Validator)

    def get(self, name, default=None):
        return self[name]


class ShipmentReceiverForm(forms.ModelForm):
    arrived_parcels = forms.ChoiceField(choices=[], required=True)

    class Meta:
        model = Shipment
        fields = ['arrived_parcels', ]

    def __init__(self, *args, **kwargs):
        super(ShipmentReceiverForm, self).__init__(*args, **kwargs)
        self.fields['arrived_parcels'].choices = [(str(x), str(x)) for x in range(1, 20)]


class SponsorAddContractForm(forms.Form):
    subject = forms.CharField(max_length=100, required=True)
    contract = forms.ModelChoiceField(SponsorshipContract.objects.all())
    manager = UserModelChoiceField(User.objects.all(), label="Manager to send to")
    message = forms.CharField(label="Message to send in signing email", widget=forms.Textarea)

    def __init__(self, sponsor, *args, **kwargs):
        self.sponsor = sponsor
        super().__init__(*args, **kwargs)

        self.fields['subject'].help_text = "Subject of contract, for example 'Training contract'. Will be prefixed with '[{}]' in all emails.".format(self.sponsor.conference.conferencename)
        self.fields['contract'].queryset = SponsorshipContract.objects.filter(conference=self.sponsor.conference, sponsorshiplevel=None)
        self.fields['manager'].queryset = self.sponsor.managers
