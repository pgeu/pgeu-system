from django import forms
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import render
from django.utils import timezone
from django.conf import settings

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.digisign.backendforms import BackendProviderForm
from postgresqleu.digisign.models import DigisignDocument, DigisignCompletedDocument, DigisignLog
from postgresqleu.digisign.util import digisign_handlers

import base64
import dateutil.parser
from decimal import Decimal
import hashlib
import hmac
import json
import time

import requests
from datetime import timedelta

from . import BaseProvider


class SignwellBackendForm(BackendProviderForm):
    apikey = forms.CharField(max_length=200, widget=forms.widgets.PasswordInput(render_value=True), label='API Key')
    applicationid = forms.CharField(max_length=200, label='Application id', required=True)
    forcetest = forms.BooleanField(label="Force test", required=False, help_text="Check this box to make ALL contracts be sent as test contracts. Test contracts are not legally binding, but free.")
    webhookurl = forms.CharField(label="Webhook URL", widget=StaticTextWidget, required=False)

    config_fields = ['apikey', 'applicationid', 'forcetest', ]
    config_readonly = ['webhookurl', ]
    config_fieldsets = [
        {
            'id': 'signwell',
            'legend': 'Signwell',
            'fields': ['apikey', 'applicationid', 'forcetest', ],
        },
        {
            'id': 'webhook',
            'legend': 'Webhook',
            'fields': ['webhookurl', ],
        },
    ]

    def fix_fields(self):
        super().fix_fields()
        self.initial['webhookurl'] = """
On the Signwell account, open up the API application and specify
<code>{}/wh/sw/{}/</code> as the event callback URL.
""".format(
            settings.SITEBASE,
            self.instance.id,
        )

    def clean(self):
        cleaned_data = super().clean()
        # Fetch the webhook api if we have an application defined

        if self.cleaned_data['applicationid']:
            impl = self.instance.get_implementation()

            # There's no searching, we have to scan them all...
            try:
                webhooks = impl.get_webhooks_for_application(self.cleaned_data['applicationid'])
                if len(webhooks) == 0:
                    self.add_error('applicationid', 'This application has no webhooks defined')
                elif len(webhooks) > 1:
                    self.add_error('applicationid', 'This application has more than one webhook defined')
                else:
                    self.instance.config['webhookid'] = webhooks[0]['id']
            except Exception as e:
                messages.warning(self.request, "Unable to get list of webhooks: {}".format(e))

        return cleaned_data


class Signwell(BaseProvider):
    backend_form_class = SignwellBackendForm
    can_send_preview = True
    can_resend = True
    has_log_details = True
    webhookcode = "sw"
    resendprompt = "Note that re-sending the contract will issue a cancel for the old contract and create a new one, which will trigger multiple emails to the recipient."

    def description_text(self, signeremail):
        return 'Signing instructions will be delivered to {}. If necessary, you will be able to re-route the signing from the provider interface to somebody else in your organisation once the process is started.'.format(signeremail)

    def send_contract(self, sender_name, sender_email, recipient_name, recipient_email, pdf, pdfname, subject, message, metadata, fielddata, expires_in, test, message_to_sender=None):
        if self.provider.config.get('forcetest', False):
            # Override test to be true if configured for enforcement.
            test = True

        payload = {
            "test_mode": "true" if test else "false",
            "files": [
                {
                    "name": pdfname,
                    "file_base64": base64.b64encode(pdf).decode(),
                }
            ],
            "name": subject,
            "subject": subject,
            "message": message.replace("\n", "<br/>"),
            "recipients": [
                {
                    "id": "1",
                    "name": recipient_name,
                    "email": recipient_email,
                },
                {
                    "id": "2",
                    "name": sender_name,
                    "email": sender_email,
                    "message": message_to_sender.replace("\n", "<br/>") if message_to_sender else message.replace("\n", "<br/>"),
                },
            ],
            "apply_signing_order": True,
            "custom_requester_name": sender_name,
            "allow_decline": True,
            "allow_reassign": True,
            "metadata": metadata,
            "fields": [fielddata.get('signwellfields', [])],
            "draft": False,
            "api_application_id": self.provider.config.get('applicationid'),
            "expires_in": expires_in,
        }

        # Add fields that only exist in prod
        if not test:
            pass

        r = requests.post('https://www.signwell.com/api/v1/documents/', json=payload, headers={
            'X-Api-Key': self.provider.config.get('apikey'),
        }, timeout=15)
        if r.status_code != 201:
            DigisignLog(
                provider=self.provider,
                document=None,
                event='internal',
                text='Could not create signing request: {}'.format(r.text),
            ).save()
            return None, "Could not create signing request: {}".format(r.text)

        return r.json()['id'], None

    def cancel_contract(self, contractid):
        try:
            r = requests.delete('https://www.signwell.com/api/v1/documents/{}/'.format(contractid), headers={
                'X-Api-Key': self.provider.config.get('apikey'),
            }, timeout=15)
            r.raise_for_status()
        except Exception as e:
            return "Exception deleting contract: {}".format(e)
        return None

    def edit_digital_fields(self, request, conference, name, pdf, fieldjson, savecallback, breadcrumbs):
        if request.method == 'GET' and 'finished' in request.GET:
            if 'signwelledit' not in fieldjson:
                return HttpResponse("No existing preview data, concurrent edit?)")

            docid = fieldjson['signwelledit']['id']
            # Fetch back the document
            r = requests.get('https://www.signwell.com/api/v1/documents/{}'.format(docid), headers={
                'X-Api-Key': self.provider.config.get('apikey'),
            }, timeout=10)
            if r.status_code != 200:
                return HttpResponse("Could not re-fetch preview document. Try again?")

            del fieldjson['signwelledit']
            fieldjson['signwellfields'] = r.json()['fields'][0]
            for f in fieldjson['signwellfields']:
                f['type'] = f['type'].lower()
                if f['type'] == 'textfield':
                    f['type'] = 'text'
                elif f['type'] == 'datefield':
                    f['type'] = 'date'

                # (possibly temporary) workaround for that signwell returns fields that are bigger than they then allow us to set
                if Decimal(f.get('height', '0')) > 34:
                    messages.warning(request, "Reduced size of field {} to 34 pixels due to signwell API limitation".format(f.get('api_id', '*unknown name*')))
                    f['height'] = "34"

            savecallback(fieldjson)

            # Delete the temporary document
            r = requests.delete('https://www.signwell.com/api/v1/documents/{}'.format(docid), headers={
                'X-Api-Key': self.provider.config.get('apikey'),
            }, timeout=10)
            if r.status_code != 204:
                DigisignLog(
                    provider=self.provider,
                    document=None,
                    event='internal',
                    text="Failed to delete preview document when complete, code {}, text {}".format(r.status_code, r.text),
                ).save()

            return None
        elif request.method == 'GET':
            return render(request, 'digisign/signwell/field_editor.html', {
                'conference': conference,
                'breadcrumbs': breadcrumbs,
            })
        elif request.method == 'POST':
            # If we already have a preview document, zap it because we'll need a new one.
            # But we ignore the error..
            if 'signwelledit' in fieldjson:
                r = requests.delete('https://www.signwell.com/api/v1/documents/{}'.format(fieldjson['signwelledit']['id']), headers={
                    'X-Api-Key': self.provider.config.get('apikey'),
                }, timeout=10)
                if r.status_code != 204:
                    DigisignLog(
                        provider=self.provider,
                        document=None,
                        event='internal',
                        text="Failed to delete existing preview document, code {}, text {}".format(r.status_code, r.text),
                    ).save()

            # Create a preview document
            subject = 'EDITPREVIEW:{}'.format(name)
            payload = {
                "test_mode": "true",
                "files": [
                    {
                        "name": "editpreview_{}.pdf".format(name),
                        "file_base64": base64.b64encode(pdf).decode(),
                    }
                ],
                "name": subject,
                "recipients": [
                    {
                        "id": "1",
                        "name": "Sponsor",
                        "email": "test1@example.com",
                    },
                    {
                        "id": "2",
                        "name": "Organisers",
                        "email": "test2@example.com",
                    },
                ],
                "allow_decline": False,
                "allow_reassign": False,
                "metadata": {"is_edit_preview": "1"},
                "draft": True,
                "api_application_id": self.provider.config.get('applicationid'),
            }

        if 'signwellfields' in fieldjson:
            payload['fields'] = [fieldjson['signwellfields']]
            for f in payload['fields'][0]:
                # Workaround: seems it gets returned mixed case but has to be specified lowercase!
                f['type'] = f['type'].lower()

                # (possibly temporary) workaround for that signwell returns fields that are bigger than they then allow us to set
                if Decimal(f.get('height', '0')) > 34:
                    messages.warning(request, "Reduced size of field {} when loading contract to 34 pixels due to signwell API limitation".format(f.get('api_id', '*unknown name*')))
                    f['height'] = "34"

        r = requests.post('https://www.signwell.com/api/v1/documents/', json=payload, headers={
            'X-Api-Key': self.provider.config.get('apikey'),
        }, timeout=15)
        if r.status_code != 201:
            return HttpResponse("Could not call signwell API, status {}, message {}".format(r.status_code, r.text))

        fieldjson['signwelledit'] = {
            'id': r.json()['id'],
            'embeddedurl': r.json()['embedded_edit_url'],
        }
        savecallback(fieldjson)

        return render(request, 'digisign/signwell/field_editor.html', {
            'conference': conference,
            'signwelledit': fieldjson['signwelledit'],
            'breadcrumbs': breadcrumbs,
        })

    def cleanup(self):
        # Get orphaned documents to remove
        r = requests.get('https://www.signwell.com/api/v1/documents', headers={
            'X-Api-Key': self.provider.config.get('apikey'),
        }, timeout=120)

        for d in r.json()['documents']:
            if d.get('metadata', {}).get('is_edit_preview', None) == '1':
                u = dateutil.parser.parse(d['updated_at'])
                if timezone.now() - u > timedelta(minutes=30):
                    print("Document {} is edit preview and older than 30 minutes, deleting".format(d['id']))
                    r = requests.delete('https://www.signwell.com/api/v1/documents/{}'.format(d['id']), headers={
                        'X-Api-Key': self.provider.config.get('apikey'),
                    }, timeout=10)
                    time.sleep(10)

    def fetch_completed(self, doc):
        print("Fetching completed document {}".format(doc.documentid))
        r = requests.get('https://www.signwell.com/api/v1/documents/{}/completed_pdf/'.format(doc.documentid), headers={
            'X-Api-Key': self.provider.config.get('apikey'),
        }, timeout=60)
        r.raise_for_status()
        DigisignCompletedDocument(document=doc, completedpdf=r.content).save()

    def process_webhook(self, request):
        if 'application/json' not in request.META['CONTENT_TYPE']:
            return HttpResponse("Invalid content type", status=400)

        try:
            j = json.loads(request.body)
        except json.decoder.JSONDecodeError:
            return HttpResponse("Invalid json", status=400)

        # Next we verify the signature
        if 'webhookid' not in self.provider.config:
            # No webhookid configured, so we just ignore it
            return HttpResponse("Ignored", status=200)

        data = j['event']['type'] + '@' + str(j['event']['time'])
        calculated_signature = hmac.new(self.provider.config['webhookid'].encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(j['event']['hash'], calculated_signature):
            return HttpResponse("Invalid signature", status=400)

        docid = j.get('data', {}).get('object', {}).get('id', None)
        if docid:
            try:
                doc = DigisignDocument.objects.get(provider=self.provider, documentid=docid)
            except DigisignDocument.DoesNotExist:
                doc = None
        else:
            doc = None

        event = j['event']['type']
        if event in ('document_viewed', 'document_declined', 'document_signed'):
            what = {
                'document_viewed': 'Document viewed by',
                'document_declined': 'Document declined by',
                'document_signed': 'Document signed by',
            }
            eventtext = "{} {}".format(
                what[event],
                "{} <{}>".format(j['event']['related_signer']['name'], j['event']['related_signer']['email']),
            )
        else:
            eventtext = event

        log = DigisignLog(
            provider=self.provider,
            document=doc,
            event=event,
            text=eventtext,
            fulldata=j,
        )
        log.save()

        if doc and doc.handler:
            if doc.handler not in digisign_handlers:
                DigisignLog(
                    provider=self.provider,
                    document=doc,
                    event='internal',
                    text='Could not find handler {} for document.'.format(doc.handler),
                    fulldata={},
                ).save()

            dhandler = digisign_handlers[doc.handler](doc)

            try:
                if event == 'document_completed':
                    dhandler.completed()
                elif event == 'document_expired':
                    dhandler.expired()
                elif event == 'document_canceled':
                    dhandler.canceled()
                elif event == 'document_declined':
                    dhandler.declined()
                elif event == 'document_signed':
                    dhandler.signed(j['event']['related_signer']['name'])
            except Exception as e:
                DigisignLog(
                    provider=self.provider,
                    document=doc,
                    event=event,
                    text='Exception processing webhook: {}'.format(e),
                    fulldata=j,
                ).save()

        return HttpResponse("OK", status=200)

    def get_webhooks_for_application(self, appid):
        # Can't search, we have to get all and traverse
        r = requests.get('https://www.signwell.com/api/v1/hooks/', headers={
            'X-Api-Key': self.provider.config.get('apikey'),
        }, timeout=10)
        r.raise_for_status()

        return [h for h in r.json() if h.get('api_application_id', None) == appid]
