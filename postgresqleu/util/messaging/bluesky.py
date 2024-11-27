from django.core.validators import ValidationError
from django import forms

from datetime import datetime, timezone, timedelta
import jwt
import re
import requests

from postgresqleu.util.image import get_image_contenttype_from_bytes

from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.confreg.backendforms import BackendSeriesMessagingForm


class BlueskyBackendForm(BackendSeriesMessagingForm):
    identifier = forms.CharField(max_length=100, required=True, label="Bluesky user email")
    password = forms.CharField(max_length=100, required=True, label="App password",
                               widget=forms.widgets.PasswordInput(render_value=True))

    @property
    def config_fields(self):
        return ['identifier', 'password']

    @property
    def config_fieldsets(self):
        return [
            {'id': 'appuser', 'legend': 'App password', 'fields': self.config_fields},
        ]

    def __init__(self, *args, **kwargs):
        self._completed_session = None
        super().__init__(*args, **kwargs)

    def clean(self):
        d = super().clean()

        # If the identifier or password has changed, we need to check them, otherwise avoid
        # doing that as it causes an API call.
        if (d['identifier'] != self.instance.config.get('identifier', None) or d['password'] != self.instance.config.get('password', None)) or 'accessjwt' not in self.instance.config:
            try:
                r = requests.post('https://bsky.social/xrpc/com.atproto.server.createSession', json={
                    'identifier': d['identifier'],
                    'password': d['password'],
                }, timeout=5)
                if r.status_code != 200:
                    self.add_error('password', 'Could not log in to bluesky: {}'.format(r.text))
                self._completed_session = r.json()
            except Exception as e:
                self.add_error('identifier', 'Exception testing bluesky password: {}'.format(e))
        return d

    def post_save(self):
        if self._completed_session:
            Bluesky.parse_and_store_session(self.instance, self._completed_session)


class Bluesky(object):
    provider_form_class = BlueskyBackendForm
    can_process_incoming = False  # XXX: TBD
    can_broadcast = True
    can_notification = False  # XXX: TBD
    direct_message_max_length = None
    typename = 'Bluesky'
    max_post_length = 300

    @classmethod
    def can_track_users_for(self, whatfor):
        return True

    @classmethod
    def get_field_help(self, whatfor):
        return 'Enter Bluesky username in the format @username.'

    @classmethod
    def validate_baseurl(self, baseurl):
        return None

    @classmethod
    def clean_identifier_form_value(self, whatfor, value):
        if not value.startswith('@'):
            raise ValidationError('Handle names must start with @')
        try:
            r = requests.get('https://bsky.social/xrpc/com.atproto.identity.resolveHandle', params={
                'handle': value.lstrip('@'),
            }, timeout=5)
            if r.status_code == 200:
                return value
            if r.status_code == 400:
                raise ValidationError('Could not validate handle: {}'.format(r.json()['message']))
            r.raise_for_status()
        except Exception as e:
            raise ValidationError('Could not validate handle: {}'.format(e))
        return value

    @classmethod
    def get_link_from_identifier(self, value):
        return value.lstrip('@')

    def __init__(self, id, config):
        self.providerid = id
        self.providerconfig = config
        self._bs = None

    @classmethod
    def parse_and_store_session(self, provider, response):
        accessjwt = response['accessJwt']
        provider.config.update({
            'accessjwt': response['accessJwt'],
            'refreshjwt': response['refreshJwt'],
            'accesstokenexpires': jwt.decode(response['accessJwt'], verify=False)['exp'],
            'refreshtokenexpires': jwt.decode(response['refreshJwt'], verify=False)['exp'],
            'handle': response['handle'],
            'did': response['did'],
        })
        provider.save(update_fields=['config'])
        return provider.config

    @property
    def bsjwt(self):
        if 'accessjwt' in self.providerconfig:
            # If the access token expires within 30 minutes, refresh it!
            if datetime.fromtimestamp(self.providerconfig['accesstokenexpires']) < datetime.utcnow() + timedelta(minutes=30):
                print("Bluesky access token expired, refreshing")
                r = requests.post(
                    'https://bsky.social/xrpc/com.atproto.server.refreshSession',
                    headers={'Authorization': 'Bearer {}'.format(self.providerconfig['refreshjwt'])},
                    timeout=5,
                )
                r.raise_for_status()
                self.providerconfig = self.parse_and_store_session(MessagingProvider.objects.get(pk=self.providerid), r.json())
        else:
            # No existing jwt, so perform login
            r = requests.post('https://bsky.social/xrpc/com.atproto.server.createSession', json={
                'identifier': self.providerconfig['identifier'],
                'password': self.providerconfig['password'],
            }, timeout=5)
            r.raise_for_status()
            self.providerconfig = self.parse_and_store_session(MessagingProvider.objects.get(pk=self.providerid), r.json())

        return self.providerconfig['accessjwt']

    def post(self, tweet, image=None, replytotweetid=None):
        post = {
            "$type": "app.bsky.feed.post",
            "text": tweet,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        facets = self._parse_facets(post["text"])
        if facets:
            post["facets"] = facets

        if image:
            r = requests.post(
                'https://bsky.social/xrpc/com.atproto.repo.uploadBlob',
                headers={
                    'Content-type': get_image_contenttype_from_bytes(image),
                    'Authorization': "Bearer " + self.bsjwt,
                },
                data=bytearray(image),
                timeout=30,
            )
            if r.status_code != 200:
                return (None, 'Image upload: {}'.format(r.text))
            post['embed'] = {
                '$type': 'app.bsky.embed.images',
                'images': [{'alt': '', 'image': r.json()['blob']}]
            }

        r = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": "Bearer " + self.bsjwt},
            json={
                "repo": self.providerconfig["did"],
                "collection": "app.bsky.feed.post",
                "record": post,
            },
            timeout=10,
        )
        r.raise_for_status()
        return (r.json()['uri'], None)

    def repost(self, tweetid):
        raise Exception("Not implemented yet")

    def send_direct_message(self, recipient_config, msg):
        raise Exception("Not implemented yet")

    def poll_public_posts(self, lastpoll, checkpoint):
        raise Exception("Not implemented yet")

    def poll_incoming_private_messages(self, lastpoll, checkpoint):
        raise Exception("Not implemented yet")

    def get_public_url(self, post):
        return 'https://bsky.app/profile/{}/post/{}'.format(
            self.providerconfig.get('handle', ''),
            post,
        )

    def check_messaging_config(self, state):
        # Check that we can get our own account info
        try:
            # Try to access the current access token. If it has expired, accessing it
            # will trigger a refresh.
            _token = self.bsjwt
        except Exception as e:
            return False, 'Could not get bluesky access token: {}'.format(e)

    def get_link(self, id):
        if id.startswith('at://'):
            # This should always be true!
            (dtd, collection, rid) = id[5:].split('/')
            if collection == 'app.bsky.feed.post':
                # This should also always be true
                return [
                    'bluesky',
                    'https://bsky.app/profile/{}/post/{}'.format(
                        self.providerconfig.get('handle', ''),
                        rid,
                    )
                ]
        return None

    # From Bluesky examples
    def _parse_urls(self, text: str):
        spans = []
        # partial/naive URL regex based on: https://stackoverflow.com/a/3809435
        # tweaked to disallow some training punctuation
        url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
        text_bytes = text.encode("UTF-8")
        for m in re.finditer(url_regex, text_bytes):
            spans.append(
                {
                    "start": m.start(1),
                    "end": m.end(1),
                    "url": m.group(1).decode("UTF-8"),
                }
            )
        return spans

    def _parse_mentions(self, text: str):
        spans = []
        # regex based on: https://atproto.com/specs/handle#handle-identifier-syntax
        mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
        text_bytes = text.encode("UTF-8")
        for m in re.finditer(mention_regex, text_bytes):
            spans.append(
                {
                    "start": m.start(1),
                    "end": m.end(1),
                    "handle": m.group(1)[1:].decode("UTF-8"),
                }
            )
        return spans

    def _parse_facets(self, text: str):
        """
        parses post text and returns a list of app.bsky.richtext.facet objects for any mentions (@handle.example.com) or URLs (https://example.com)

        indexing must work with UTF-8 encoded bytestring offsets, not regular unicode string offsets, to match Bluesky API expectations
        """
        facets = []
        for m in self._parse_mentions(text):
            resp = requests.get(
                "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": m["handle"]},
                timeout=10,
            )
            # if handle couldn't be resolved, just skip it! will be text in the post
            if resp.status_code == 400:
                continue
            did = resp.json()["did"]
            facets.append(
                {
                    "index": {
                        "byteStart": m["start"],
                        "byteEnd": m["end"],
                    },
                    "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
                }
            )
        for u in self._parse_urls(text):
            facets.append(
                {
                    "index": {
                        "byteStart": u["start"],
                        "byteEnd": u["end"],
                    },
                    "features": [
                        {
                            "$type": "app.bsky.richtext.facet#link",
                            # NOTE: URI ("I") not URL ("L")
                            "uri": u["url"],
                        }
                    ],
                }
            )
        return facets
