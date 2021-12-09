from django import forms
from django.utils import timezone
from django.utils.html import strip_tags

import requests_oauthlib
import requests
import dateutil.parser

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.forms import LinkForCodeField
from postgresqleu.util.oauthapps import get_oauth_client, get_oauth_secret
from postgresqleu.util.models import OAuthApplication
from postgresqleu.util.messaging import re_token

from postgresqleu.confreg.backendforms import BackendSeriesMessagingForm
from postgresqleu.confreg.models import ConferenceRegistration

from .util import send_reg_direct_message


# We always ask for this scope
MASTODON_SCOPES = "read write:statuses write:media"


class MastodonBackendForm(BackendSeriesMessagingForm):
    initialconfig = LinkForCodeField(label='Get authorization code')
    mastodoninfo = forms.CharField(widget=StaticTextWidget, label="Account information", required=False)

    def __init__(self, *args, **kwargs):
        self.baseurl = None
        super().__init__(*args, **kwargs)

    def fix_fields(self):
        super().fix_fields()

        if self.baseurl:
            self.instance.config['baseurl'] = self.baseurl.rstrip('/')

        if self.instance.config.get('token', None):
            del self.fields['initialconfig']
            self.config_fields = ['mastodoninfo', ]
            self.config_fieldsets = [
                {'id': 'mastodon', 'legend': 'Mastodon', 'fields': ['mastodoninfo', ]},
            ]
            self.config_readonly_fields = ['mastodoninfo', ]

            try:
                if 'username' not in self.instance.config:
                    self.instance.config.update(Mastodon(self.instance.id, self.instance.config).get_account_info())
                    self.instance.save(update_fields=['config'])
                selfinfo = "Connected to mastodon account @{}.".format(self.instance.config['username'])
            except Exception as e:
                selfinfo = "ERROR verifying Mastodon access: {}".format(e)

            self.initial.update({
                'mastodoninfo': selfinfo,
            })
        else:
            # Not configured yet, so prepare for it!
            del self.fields['mastodoninfo']
            self.config_fields = ['initialconfig', ]
            self.config_fieldsets = [
                {'id': 'mastodon', 'legend': 'Mastodon', 'fields': ['initialconfig', ]},
            ]
            self.nosave_fields = ['initialconfig', ]

            # Ugly power-grab here, but let's see what's in our POST
            if self.request.POST.get('initialconfig', None):
                # Token is included, so don't try to get a new one
                self.fields['initialconfig'].widget.authurl = self.request.session['authurl']
            else:
                auth_url, state = self._get_oauth_session().authorization_url('{}/oauth/authorize'.format(self.instance.config['baseurl']))
                self.request.session['authurl'] = auth_url

                self.fields['initialconfig'].widget.authurl = auth_url

    def clean(self):
        d = super().clean()
        if d.get('initialconfig', None):
            # We have received an initial config, so try to attach ourselves to mastodon
            try:
                tokens = self._get_oauth_session().fetch_token(
                    '{}/oauth/token'.format(self.instance.config['baseurl']),
                    code=d.get('initialconfig'),
                    client_secret=get_oauth_secret(self.instance.config['baseurl']),
                    scopes=MASTODON_SCOPES
                )

                self.instance.config['token'] = tokens['access_token']
                del self.request.session['authurl']
                self.request.session.modified = True
            except Exception as e:
                self.add_error('initialconfig', 'Could not set up Mastodon: {}'.format(e))
                self.add_error('initialconfig', 'You probably have to restart the process')
        return d

    def _get_oauth_session(self):
        return requests_oauthlib.OAuth2Session(
            get_oauth_client(self.instance.config['baseurl']),
            redirect_uri='urn:ietf:wg:oauth:2.0:oob',
            scope=MASTODON_SCOPES
        )


class Mastodon(object):
    provider_form_class = MastodonBackendForm
    can_process_incoming = True
    can_broadcast = True
    can_notification = True
    direct_message_max_length = 450  # 500 is lenght, draw down some to handle username

    @classmethod
    def validate_baseurl(self, baseurl):
        if not OAuthApplication.objects.filter(name='mastodon', baseurl=baseurl).exists():
            return 'Global OAuth credentials for {} missing'.format(baseurl)

    @property
    def max_post_length(self):
        return 500

    def __init__(self, providerid, config):
        self.providerid = providerid
        self.providerconfig = config

        self.sess = requests.Session()
        self.sess.headers.update({
            'Authorization': 'Bearer {}'.format(self.providerconfig['token']),
        })

    def _api_url(self, url):
        return '{}{}'.format(self.providerconfig['baseurl'], url)

    def _get(self, url, *args, **kwargs):
        return self.sess.get(self._api_url(url), *args, **kwargs)

    def _post(self, url, *args, **kwargs):
        return self.sess.post(self._api_url(url), *args, **kwargs)

    def get_account_info(self):
        r = self._get('/api/v1/accounts/verify_credentials')
        r.raise_for_status()
        j = r.json()
        return {
            'username': j['username'],
        }

    def post(self, toot, image=None, replytotweetid=None):
        d = {
            'status': toot,
            'visibility': 'public',
        }
        if replytotweetid:
            d['in_reply_to_id'] = replytotweetid

        if image:
            r = self._post('/api/v1/media', files={
                'file': bytearray(image),
            })
            if r.status_code != 200:
                return (False, 'Media upload: {}'.format(r.text))
            d['media_ids'] = [int(r.json()['id']), ]

        r = self._post('/api/v1/statuses', json=d)
        if r.status_code != 200:
            return (None, r.text)

        return (r.json()['id'], None)

    def repost(self, postid):
        r = self._post('/api/v1/statuses/{}/reblog'.format(postid))
        if r.status_code != 200:
            return (None, r.text)
        return (True, None)

    def send_direct_message(self, recipient_config, msg):
        d = {
            'status': '@{} {}'.format(recipient_config['username'], msg),
            'visibility': 'direct',
        }

        r = self._post('/api/v1/statuses', json=d)
        r.raise_for_status()

    def poll_public_posts(self, lastpoll, checkpoint):
        p = {
            'limit': 200,  # If it's this many, we should give up
            'exclude_types[]': ['follow', 'favourite', 'reblog', 'poll', 'follow_request'],
        }
        if checkpoint:
            p['since_id'] = checkpoint

        r = self._get('/api/v1/notifications', params=p)
        r.raise_for_status()

        for n in r.json():
            if n['type'] != 'mention':
                # Sometimes  Mastodon may include a type that we don't know about, since it hadn't yet
                # been added to the exclude_types. So ignore them if they show up.
                continue

            s = n['status']
            d = {
                'id': int(s['id']),
                'datetime': dateutil.parser.parse(s['created_at']),
                'text': strip_tags(s['content']),
                'replytoid': s['in_reply_to_id'] and int(s['in_reply_to_id']) or None,
                'author': {
                    'name': s['account']['display_name'] or s['account']['username'],
                    'username': s['account']['username'],
                    'id': s['account']['id'],
                    'imageurl': s['account']['avatar_static'],
                },
                'media': [m['url'] for m in s['media_attachments']],
            }
            # (mastodon doesn't have quoted status, so just leave that one non-existing)
            yield d

    def poll_incoming_private_messages(self, lastpoll, checkpoint):
        p = {
            'limit': 40,
        }
        if checkpoint:
            p['since_id'] = checkpoint

        r = self._get('/api/v1/conversations', params=p)
        r.raise_for_status()

        j = r.json()
        for c in j:
            if len(c['accounts']) > 1:
                # Can't handle group messages
                continue
            ls = c['last_status']
            self.process_incoming_dm(ls)

        if len(j):
            # For some reason, it paginates by last_status->id, and not by id. Go figure.
            return timezone.now(), max((c['last_status']['id'] for c in j))
        else:
            return timezone.now(), checkpoint

    def process_incoming_dm(self, msg):
        for m in re_token.findall(msg['content']):
            try:
                reg = ConferenceRegistration.objects.get(regtoken=m)

                reg.messaging_config = {
                    'username': msg['account']['username'],
                }
                reg.save(update_fields=['messaging_config'])

                send_reg_direct_message(reg, 'Hello! This account is now configured to receive notifications for {}'.format(reg.conference))
            except ConferenceRegistration.DoesNotExist:
                pass

    def get_public_url(self, post):
        return '{}@{}/{}'.format(self.providerconfig['baseurl'], post.author_screenname, post.statusid)

    def get_attendee_string(self, token, messaging, attendeeconfig):
        if 'username' in attendeeconfig:
            return "Your notifications will be sent to @{}.".format(attendeeconfig['username']), None
        else:
            return 'mastodon_invite.html', {
                'mastodonname': self.providerconfig['username'],
                'token': token,
            }

    def check_messaging_config(self, state):
        return True, ''
