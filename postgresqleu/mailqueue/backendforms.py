from django import forms

from email.parser import Parser

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.mailqueue.models import QueuedMail


class BackendMailqueueForm(BackendForm):
    decoded = forms.CharField(label="Decoded message", widget=StaticTextWidget(monospace=True))

    list_fields = ['sendtime', 'sender', 'receiver', 'subject', ]
    helplink = 'mail'

    class Meta:
        model = QueuedMail
        fields = ['sender', 'receiver', 'fullmsg', ]

    def fix_fields(self):
        self.initial['decoded'] = self.parsed_content().decode('utf8', errors='ignore').replace("\n", "<br/>")

    def parsed_content(self):
        # We only try to parse the *first* piece, because we assume
        # all our emails are trivial.
        try:
            parser = Parser()
            msg = parser.parsestr(self.instance.fullmsg)
            b = msg.get_payload(decode=True)
            if b:
                return b

            pl = msg.get_payload()
            for p in pl:
                b = p.get_payload(decode=True)
                if b:
                    return b
            return "Could not find body"
        except Exception as e:
            return "Failed to get body: %s" % e
