from django import forms
from django.forms import ValidationError
from django.core.signing import Signer, BadSignature

import cPickle
import base64


class _ValidatorField(forms.Field):
	required=True
	widget=forms.HiddenInput

class ConcurrentProtectedModelForm(forms.ModelForm):
	_validator = _ValidatorField()

	def _filter_initial(self):
		# self.initial will include things given in the URL after ?, so filter it to
		# inly include items that are actually form fields.
		return {k:v for k,v in self.initial.items() if k in self.fields.keys()}

	def __init__(self, *args, **kwargs):
		r = super(ConcurrentProtectedModelForm, self).__init__(*args, **kwargs)

		self.fields['_validator'].initial = Signer().sign(base64.urlsafe_b64encode(cPickle.dumps(self._filter_initial(), -1)))

		return r

	def clean(self):
		# Process the form itself
		data = super(ConcurrentProtectedModelForm, self).clean()

		# Fetch the list of values from the currernt object in the db
		i = self._filter_initial()
		try:
			s = Signer().unsign(self.cleaned_data['_validator'])
			b = base64.urlsafe_b64decode(s.encode('utf8'))
			d = cPickle.loads(b)
			for k,v in d.items():
				if i[k] != v:
					raise ValidationError("Concurrent modification of field {0}. Please reload the form and try again.".format(k))
		except BadSignature:
			raise ValidationError("Form has been tampered with!")
		except TypeError:
			raise ValidationError("Bad serialized form state")
		except cPickle.UnpicklingError:
			raise ValidationError("Bad serialized python form state")

		return data
