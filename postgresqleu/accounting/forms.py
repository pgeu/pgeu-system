from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet


from models import JournalEntry, JournalItem, Object, JournalUrl


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
    debit = forms.DecimalField(max_digits=10, decimal_places=2, validators=[PositiveValidator, ], required=False)
    credit = forms.DecimalField(max_digits=10, decimal_places=2, validators=[PositiveValidator, ], required=False)

    def __init__(self, *args, **kwargs):
        super(JournalItemForm, self).__init__(*args, **kwargs)
        if self.instance.amount:
            if self.instance.amount > 0:
                self.fields['debit'].initial = self.instance.amount
            elif self.instance.amount < 0:
                self.fields['credit'].initial = -self.instance.amount
        self.fields['account'].widget.attrs['class'] = 'dropdownbox'
        self.fields['object'].widget.attrs['class'] = 'dropdownbox'
        self.fields['object'].queryset = Object.objects.filter(active=True)
        self.fields['description'].widget.attrs['class'] = 'descriptionbox form-control'
        self.fields['debit'].widget.attrs['class'] = 'debitbox form-control'
        self.fields['credit'].widget.attrs['class'] = 'creditbox form-control'

    class Meta:
        model = JournalItem
        exclude = ('amount', )

    def clean(self):
        if not self.cleaned_data:
            return
        if not self.cleaned_data.has_key('debit') or not self.cleaned_data.has_key('credit'):
            # This means there is an error elsewhere!
            return self.cleaned_data
        if self.cleaned_data['debit'] and self.cleaned_data['credit']:
            raise ValidationError("Can't specify both debit and credit!")
        if not self.cleaned_data['debit'] and not self.cleaned_data['credit']:
            raise ValidationError("Must specify either debit or credit!")
        return self.cleaned_data

    def clean_object(self):
        if self.cleaned_data.has_key('account'):
            if self.cleaned_data['account'].objectrequirement == 1:
                # object is required
                if not self.cleaned_data['object']:
                    raise ValidationError("Account %s requires an object to be specified" % self.cleaned_data['account'].num)
            elif self.cleaned_data['account'].objectrequirement == 2:
                # object is forbidden
                if self.cleaned_data['object']:
                    raise ValidationError("Account %s does not allow an object to be specified" % self.cleaned_data['account'].num)
        return self.cleaned_data['object']

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
        debit = self.cleaned_data.has_key('debit') and self.cleaned_data['debit'] or 0
        credit = self.cleaned_data.has_key('credit') and self.cleaned_data['credit'] or 0
        return debit - credit


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


class JournalUrlForm(forms.ModelForm):
    class Meta:
        model = JournalUrl
        exclude = ()

    def __init__(self, *args, **kwargs):
        super(JournalUrlForm, self).__init__(*args, **kwargs)
        self.fields['url'].widget.attrs['class'] = 'form-control'
