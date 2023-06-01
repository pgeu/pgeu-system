from django import forms

from collections import OrderedDict

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.mailqueue.models import QueuedMail
from postgresqleu.mailqueue.util import parse_mail_content, recursive_parse_attachments_from_message


class BackendMailqueueAttachmentManager:
    title = 'Attachments'
    singular = 'attachment'
    can_add = False

    def get_list(self, instance):
        for id, name, ctype, content in recursive_parse_attachments_from_message(instance.parsed_msg):
            yield id, name, ctype


class BackendMailqueueForm(BackendForm):
    decoded = forms.CharField(label="Decoded message", widget=StaticTextWidget(monospace=True))

    list_fields = ['sendtime', 'sender', 'receiver', 'subject', ]
    helplink = 'mail'
    readonly_fields = ['sender', 'receiver', 'subject', 'fullmsg', ]
    linked_objects = OrderedDict({
        'attachments': BackendMailqueueAttachmentManager(),
    })

    class Meta:
        model = QueuedMail
        fields = ['sender', 'receiver', 'subject', 'fullmsg', ]

    def fix_fields(self):
        self.initial['decoded'] = self.parsed_content().decode('utf8', errors='ignore').replace("\n", "<br/>")

    def parsed_content(self):
        if not hasattr(self.instance, 'parsed_msg') or not hasattr(self.instance, 'parsed_txt'):
            self.instance.parsed_msg, self.instance.parsed_txt = parse_mail_content(self.instance.fullmsg)

        return self.instance.parsed_txt
