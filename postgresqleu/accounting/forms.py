from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet


from models import JournalEntry, JournalItem, Object

class JournalEntryForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(JournalEntryForm, self).__init__(*args, **kwargs)
		self.fields['date'].widget.attrs['class'] = 'datepicker'
		self.fields['date'].widget.attrs['autofocus'] = 'autofocus'

	class Meta:
		model = JournalEntry
		exclude = ('year', 'seq', )


def PositiveValidator(v):
	if v <= 0:
		raise ValidationError("Value must be a positive integer")

class JournalItemForm(forms.ModelForm):
	debit = forms.DecimalField(max_digits=10, decimal_places=2, validators=[PositiveValidator,], required=False)
	credit = forms.DecimalField(max_digits=10, decimal_places=2, validators=[PositiveValidator,], required=False)

	def __init__(self, *args, **kwargs):
		super(JournalItemForm, self).__init__(*args, **kwargs)
		if self.instance.amount:
			if self.instance.amount > 0:
				self.fields['debit'].initial = self.instance.amount
			elif self.instance.amount <0:
				self.fields['credit'].initial = -self.instance.amount
		self.fields['account'].widget.attrs['class'] = 'itembox accountbox chosenbox'
		self.fields['object'].widget.attrs['class'] = 'itembox objectbox chosenbox'
		self.fields['object'].queryset = Object.objects.filter(active=True)
		self.fields['description'].widget.attrs['class'] = 'itembox descriptionbox'
		self.fields['debit'].widget.attrs['class'] = 'itembox debitbox'
		self.fields['credit'].widget.attrs['class'] = 'itembox creditbox'

	class Meta:
		model = JournalItem
		exclude = ('amount', )

	def clean(self):
		if not self.cleaned_data: return
		if not self.cleaned_data.has_key('debit') or not self.cleaned_data.has_key('credit'):
			# This means there is an error elsewhere!
			return self.cleaned_data
		if self.cleaned_data['debit'] and self.cleaned_data['credit']:
			raise ValidationError("Can't specify both debit and credit!")
		if not self.cleaned_data['debit'] and not self.cleaned_data['credit']:
			raise ValidationError("Must specify either debit or credit!")
		return self.cleaned_data

	def save(self, commit=True):
		instance = super(JournalItemForm, self).save(commit=False)
		if self.cleaned_data['debit']:
			instance.amount = self.cleaned_data['debit']
		else:
			instance.amount = -self.cleaned_data['credit']
		if commit:
			instance.save()
		return instance

	def get_amount(self):
		if not hasattr(self, 'cleaned_data'):
			return 0
		if not self.cleaned_data:
			return 0
		if self.cleaned_data['DELETE']:
			return 0
		debit = self.cleaned_data['debit'] and self.cleaned_data['debit'] or 0
		credit = self.cleaned_data['credit'] and self.cleaned_data['credit'] or 0
		return debit-credit

class JournalItemFormset(BaseInlineFormSet):
	def clean(self):
		super(JournalItemFormset, self).clean()
		if len(self.forms) == 0:
			raise ValidationError("Cannot save with no entries")
		s = sum([f.get_amount() for f in self.forms])
		if s != 0:
			raise ValidationError("Journal entry does not balance, sum is %s!" % s)
		n = sum([1 for f in self.forms if f.get_amount() != 0])
		if n == 0:
			raise ValidationError("Journal entry must have at least one item!")
