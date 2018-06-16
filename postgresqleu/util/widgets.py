from django import forms
from django.utils.safestring import mark_safe

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
