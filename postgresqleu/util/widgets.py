from django import forms
from django.forms.widgets import TextInput
from django.core.files.uploadedfile import UploadedFile
from django.utils.safestring import mark_safe
from django.template import loader

import base64
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
        return mark_safe(''.join(output))


class PrettyPrintJsonWidget(forms.Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        # This is mighty ugly -- we parse the json and then turn it back into json.
        # Luckily this isn't called often :)
        try:
            if value is not None:
                if isinstance(value, dict):
                    # Already a dict, so just turn it into json
                    value = json.dumps(value, indent=2)
                else:
                    value = json.dumps(json.loads(value), indent=2)
        except ValueError:
            # Don't try to do anything if it's not valid json
            pass
        t = super(PrettyPrintJsonWidget, self).render(name, value, attrs, renderer)
        return t


class MonospaceTextarea(forms.Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        attrs['class'] = "{0} text-monospace".format(attrs.get('class', ''))
        return super(MonospaceTextarea, self).render(name, value, attrs, renderer)


class TagOptionsTextWidget(forms.Textarea):
    def __init__(self, taglist, *args, **kwargs):
        self.taglist = taglist
        super(TagOptionsTextWidget, self).__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        t = super(TagOptionsTextWidget, self).render(name, value, attrs, renderer)
        return t + mark_safe('<div class="textarea-tagoptions-list" data-areaid="{}">Suggested tags: {}</div>'.format(
            attrs['id'],
            "".join(('<span class="label label-success tagoption">{}</span>'.format(t) for t in self.taglist))
        ))


class EmailTextWidget(forms.Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        attrs.update({
            "cols": "72",
            "class": "{0} textarea-mail".format(attrs.get('class', '')),
            "wrap": "hard",
        })
        t = super(EmailTextWidget, self).render(name, value, attrs, renderer)
        return mark_safe('<div class="textarea-mail-prefix">This text area is sized to the correct width of an email! Automatic line wrappings are preserved.</div>') + t


class InlineImageUploadWidget(forms.ClearableFileInput):
    clear_checkbox_label = "Remove image"

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)
        if value and not isinstance(value, UploadedFile):
            context['widget']['value'] = base64.b64encode(value).decode('ascii')
            context['widget']['imagetype'] = 'image/png' if bytes(value[:8]) == b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A' else 'image/jpg'
        return mark_safe(loader.render_to_string('confreg/widgets/inline_photo_upload_widget.html', context))


class InlinePdfUploadWidget(forms.ClearableFileInput):
    clear_checkbox_label = "Remove PDF"

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)
        if value and not isinstance(value, UploadedFile):
            context['widget']['value'] = base64.b64encode(value).decode('ascii')
        return mark_safe(loader.render_to_string('confreg/widgets/inline_pdf_upload_widget.html', context))


class AdminJsonWidget(PrettyPrintJsonWidget):
    def render(self, name, value, attrs=None, renderer=None):
        attrs['cols'] = 100
        return super(AdminJsonWidget, self).render(name, value, attrs, renderer)


class StaticTextWidget(TextInput):
    def __init__(self, *args, **kwargs):
        self.monospace = kwargs.pop('monospace', False)

        super(StaticTextWidget, self).__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        if self.monospace:
            return mark_safe('<div class="text-monospace">{0}</div>'.format(value))
        else:
            return mark_safe(value)


class TestButtonWidget(TextInput):
    template_name = 'forms/widgets/test_button_widget.html'


class Bootstrap4CheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = 'forms/widgets/bs4_checkbox_select.html'


class Bootstrap4HtmlDateTimeInput(forms.DateTimeInput):
    template_name = 'forms/widgets/bs4_datetime_input.html'


class LinkForCodeWidget(TextInput):
    template_name = 'forms/widgets/linkforcode_widget.html'

    def get_context(self, name, value, attrs):
        d = super().get_context(name, value, attrs)
        d['authurl'] = self.authurl
        return d


class SubmitButtonWidget(forms.Widget):
    template_name = 'forms/widgets/submitbutton_widget.html'

    def get_context(self, name, value, attrs):
        d = super().get_context(name, value, attrs)
        d['label'] = self.label
        d['prefixparagraph'] = self.prefixparagraph
        return d


class SelectSetValueWidget(forms.Select):
    option_template_name = 'forms/widgets/select_set_value_option.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        attrs['data-set-form-field'] = 'id_{}'.format(self.setvaluefield)
        context = super().get_context(name, value, attrs)
        context['setmap'] = self.setvalues
        return context
