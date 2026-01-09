from django import forms
from django.utils import timezone

from collections import OrderedDict

from postgresqleu.util.widgets import StaticTextWidget, StaticHtmlPreviewWidget
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.mailqueue.models import QueuedMail
from postgresqleu.mailqueue.util import parse_mail_content, recursive_parse_attachments_from_message
from postgresqleu.mailqueue.util import re_cid_image


class BackendMailqueueAttachmentManager:
    title = 'Attachments'
    singular = 'attachment'
    can_add = False

    def get_list(self, instance):
        for id, name, ctype, content in recursive_parse_attachments_from_message(instance.parsed_msg):
            yield id, name, ctype


class BackendMailqueueForm(BackendForm):
    decoded = forms.CharField(label="Decoded message", widget=StaticTextWidget(monospace=True))
    htmldecoded = forms.CharField(label="HTML message", widget=StaticHtmlPreviewWidget())

    list_fields = ['sendtime', 'regtime', 'sendtime', 'sender', 'receiver', 'subject', ]
    helplink = 'mail'
    readonly_fields = ['sender', 'receiver', 'sendtime', 'subject', 'fullmsg', ]
    linked_objects = OrderedDict({
        'attachments': BackendMailqueueAttachmentManager(),
    })

    class Meta:
        model = QueuedMail
        fields = ['sender', 'receiver', 'sendtime', 'subject', 'fullmsg', ]

    def fix_fields(self):
        self.initial['decoded'] = self.parsed_content()
        self.initial['htmldecoded'] = self.parsed_html()

    # Replacing the cid images using a regexp is kind of ugly, but it does work...
    def _ensure_parsed(self):
        if not hasattr(self.instance, 'parsed_msg') or not hasattr(self.instance, 'parsed_txt'):
            self.instance.parsed_msg, self.instance.parsed_txt, self.instance.parsed_html = parse_mail_content(self.instance.fullmsg)
            self.instance.parsed_txt = self.instance.parsed_txt.decode('utf8', errors='ignore').replace("\n", "<br/>")
            self.instance.parsed_html = re_cid_image.sub(
                self._replace_cid_reference,
                self.instance.parsed_html.decode('utf8', errors='ignore'),
            )

    def _replace_cid_reference(self, m):
        return m.group(1) + 'attachments/{}/'.format(m.group(2).replace('cid:', '')) + m.group(3)

    def parsed_content(self):
        self._ensure_parsed()
        return self.instance.parsed_txt

    def parsed_html(self):
        self._ensure_parsed()
        return self.instance.parsed_html

    @classmethod
    def get_rowclass_and_title(self, obj, cache):
        if obj.sendtime < timezone.now():
            return "warning", None
        else:
            return "", None
