from django import forms
from django.forms.widgets import TextInput
from django.utils.safestring import mark_safe

import datetime
import json

class HtmlDateInput(TextInput):
	def __init__(self, *args, **kwargs):
		kwargs.update({'attrs': {'type': 'date', 'required-pattern': '[0-9]{4}-[0-9]{2}-[0-9]{2}'}})
		super(HtmlDateInput, self).__init__(*args, **kwargs)

	def format_value(self, val):
		if isinstance(val, datetime.datetime):
			val = val.date()
		return super(HtmlDateInput, self).format_value(val)

class RequiredFileUploadWidget(forms.FileInput):
	def __init__(self, filename=None, attrs=None):
		self.filename = filename
		super(RequiredFileUploadWidget, self).__init__(attrs)

	def render(self, name, value, attrs=None):
		output = []
		if value and hasattr(value, 'url'):
			output.append('Current file: <a href="{0}">'.format(value.url))
			if self.filename:
				output.append(self.filename)
			else:
				output.append(value.name)
			output.append('</a><br/>')
		output.append("Upload new file: ")
		output.append(super(RequiredFileUploadWidget, self).render(name, value, attrs))
		return mark_safe(u''.join(output))

class PrettyPrintJsonWidget(forms.Textarea):
	def render(self, name, value, attrs=None, renderer=None):
		# This is mighty ugly -- we parse the json and then turn it back into json.
		# Luckily this isn't called often :)
		try:
			value = json.dumps(json.loads(value), indent=2)
		except ValueError:
			# Don't try to do anything if it's not valid json
			pass
		t = super(PrettyPrintJsonWidget, self).render(name, value, attrs, renderer)
		return t

class AdminJsonWidget(PrettyPrintJsonWidget):
	def render(self, name, value, attrs=None, renderer=None):
		attrs['cols'] = 100
		return super(AdminJsonWidget, self).render(name, value, attrs, renderer)
