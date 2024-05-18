from django.http import HttpResponse, Http404, HttpResponseRedirect
from django import forms
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils.timesince import timeuntil
from django.utils import timezone

from datetime import datetime, timedelta
import re
import requests
import requests_oauthlib
import time

from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.oauthapps import get_oauth_client, get_oauth_secret
from postgresqleu.util.time import datetime_string
from postgresqleu.util.widgets import StaticTextWidget

from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.confreg.backendforms import BackendSeriesMessagingForm

# Scopes to request when fetching token
LINKEDIN_SCOPE = 'r_organization_social,w_organization_social'


class LinkedinBackendForm(BackendSeriesMessagingForm):
    linkedininfo = forms.CharField(widget=StaticTextWidget, label="Account information", required=False)
    pageid = forms.IntegerField(required=True, help_text="The id number of the page to post to. Can be retrieved from the URL of the page.", label='Page ID')

    exclude_fields_from_validation = ['linkedininfo', ]

    @property
    def config_fields(self):
        f = ['linkedininfo', ]
        if self.instance.config.get('token', None):
            return f + ['pageid', ]
        else:
            return f

    @property
    def config_fieldsets(self):
        return [
            {'id': 'linkedin', 'legend': 'Linkedin', 'fields': self.config_fields},
        ]

    @property
    def config_readonly_fields(self):
        return ['linkedininfo', ]

    def fix_fields(self):
        super().fix_fields()

        auth_url, state = requests_oauthlib.OAuth2Session(
            get_oauth_client('https://api.linkedin.com'),
            redirect_uri='{}/oauth_return/messaging/{}/'.format(settings.SITEBASE, self.instance.id),
            scope=LINKEDIN_SCOPE,
        ).authorization_url('https://www.linkedin.com/oauth/v2/authorization')

        if self.instance.config.get('token', None):
            tokenexpires = timezone.make_aware(datetime.fromtimestamp(self.instance.config.get('token_expires')))
            refreshtokenexpires = timezone.make_aware(datetime.fromtimestamp(self.instance.config.get('refresh_token_expires')))

            self.initial.update({
                'linkedininfo': 'Connected to Linkedin account.<br/>Current access token will expire in {} (on {}), and will be automatically renewed until {}, after which it must be manually re-authenticated.<br/>To re-athenticate, click <a href="{}">this link</a> and log in with a Linkedin account with the appropriate permissions.'.format(
                    timeuntil(tokenexpires),
                    datetime_string(tokenexpires),
                    datetime_string(refreshtokenexpires),
                    auth_url,
                ),
            })
        else:
            self.remove_field('pageid')

            if not self.instance.id:
                self.initial.update({
                    'linkedininfo': 'Not connected. Save the provider first, and then return here to configure.',
                })
            else:
                # Create an oauth URL for access
                # (XXX: we don't store the state for verification here, which maybe we should, but we don't care that much here)

                self.initial.update({
                    'linkedininfo': 'Not connected. Please follow <a href="{}">this link</a> and authorize access to Linkedin.'.format(auth_url),
                })

    def clean(self):
        d = super().clean()
        if d.get('active', False):
            if not d.get('pageid', 0):
                self.add_error('active', 'Cannot activate without a pageid')

            # Unfortunately, the linkedin api gives us no good way to validate that we have access to a page. If we could
            # work without a rate limit, we could create an unpublished post and then delete it, but with the default rate limiting that
            # is very wasteful so we skip it for now.

        return d


class Linkedin(object):
    provider_form_class = LinkedinBackendForm
    can_process_incoming = False
    can_broadcast = True
    can_notification = False
    direct_message_max_length = None
    typename = 'Linkedin'
    max_post_length = 3000

    re_adminpage_url = re.compile(r'https://www.linkedin.com/company/(\d+)/.*')
    re_publicpage_url = re.compile(r'https://www.linkedin.com/company/([^/]+)/.*')

    @classmethod
    def can_track_users_for(self, whatfor):
        return False

    @classmethod
    def validate_baseurl(self, baseurl):
        return None

    @classmethod
    def clean_identifier_form_value(self, whatfor, value):
        raise Exception("Not implemented")

    @classmethod
    def get_link_from_identifier(self, value):
        return 'https://linkedin.com/company/{}'.format(value)

    def __init__(self, id, config):
        self.providerid = id
        self.providerconfig = config
        self._sess = None
        if 'pageid' in self.providerconfig:
            self.urn = 'urn:li:organization:{}'.format(self.providerconfig['pageid'])
        else:
            self.urn = None

    @property
    def sess(self):
        if self._sess is None:
            self._sess = requests.Session()
            self._sess.headers.update({
                'Authorization': 'Bearer {}'.format(self.providerconfig['token']),
                'LinkedIn-Version': '202405',
            })
        return self._sess

    def _api_url(self, url):
        return 'https://api.linkedin.com/{}'.format(url)

    def _get(self, url, *args, **kwargs):
        return self.sess.get(self._api_url(url), timeout=30, *args, **kwargs)

    def _post(self, url, *args, **kwargs):
        return self.sess.post(self._api_url(url), timeout=30, *args, **kwargs)

    def oauth_return(self, request):
        try:
            tokens = requests_oauthlib.OAuth2Session(
                get_oauth_client('https://api.linkedin.com'),
                redirect_uri='{}/oauth_return/messaging/{}/'.format(settings.SITEBASE, self.providerid),
                scope=LINKEDIN_SCOPE,
            ).fetch_token(
                'https://www.linkedin.com/oauth/v2/accessToken',
                code=request.GET['code'],
                client_secret=get_oauth_secret('https://api.linkedin.com'),
                scopes=LINKEDIN_SCOPE,
            )
        except Exception as e:
            return 'Could not fetch token: {}'.format(e)

        m = get_object_or_404(MessagingProvider, pk=self.providerid)
        m.config.update({
            'token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'token_expires': int(tokens['expires_in'] + time.time()),
            'refresh_token_expires': int(tokens['refresh_token_expires_in'] + time.time()),
        })
        m.save(update_fields=['config'])

    def post(self, text, image=None, replytotweetid=None):
        if not self.urn:
            # Can't post without an URN
            return

        d = {
            'author': self.urn,
            'commentary': text,
            'visibility': 'PUBLIC',
            'distribution': {
                'feedDistribution': 'MAIN_FEED',
            },
            'lifecycleState': 'PUBLISHED',
        }

        if image:
            # Initiate multi-step image upload
            r = self._post('rest/images', params={'action': 'initializeUpload'}, json={
                'initializeUploadRequest': {
                    'owner': self.urn,
                }
            })
            if r.status_code != 200:
                return (None, 'Failed to initialize image upload: {}'.format(r.text))
            ir = self.sess.put(r.json()['value']['uploadUrl'], bytearray(image), timeout=60)
            if ir.status_code != 201:
                return (None, 'Failed to upload image: {}'.format(ir.text))
            # Upload complete, we can use it!
            d['content'] = {
                'media': {
                    'id': r.json()['value']['image'],
                },
            }
        r = self._post('rest/posts', json=d)
        if r.status_code != 201:
            return (None, r.text)

        # Format of id is urn:li:share:7196857142283268096
        return (r.headers['x-linkedin-id'], None)

    def repost(self, tweetid):
        raise Exception("Not implemented")

    def send_direct_message(self, recipient_config, msg):
        raise Exception("Not implemented")

    def poll_public_posts(self, lastpoll, checkpoint):
        raise Exception("Not implemented")

    def poll_incoming_private_messages(self, lastpoll, checkpoint):
        raise Exception("Not implemented")

    def get_regconfig_from_dm(self, dm):
        raise Exception("Not implemented")

    def get_regdisplayname_from_config(self, config):
        raise Exception("Not implemented")

    def get_public_url(self, post):
        return 'https://www.linkedin.com/feed/update/urn:li:share:{}/'.format(post.statusid)

    def get_attendee_string(self, token, messaging, attendeeconfig):
        raise Exception("Not implemented")

    def refresh_access_token(self):
        r = requests.post('https://www.linkedin.com/oauth/v2/accessToken', data={
            'grant_type': 'refresh_token',
            'refresh_token': self.providerconfig['refresh_token'],
            'client_id': get_oauth_client('https://api.linkedin.com'),
            'client_secret': get_oauth_secret('https://api.linkedin.com'),
        }, timeout=30)
        if r.status_code == 200:
            tokens = r.json()
            provider = MessagingProvider.objects.get(pk=self.providerid)
            provider.config.update({
                'token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'token_expires': int(tokens['expires_in'] + time.time()),
                'refresh_token_expires': int(tokens['refresh_token_expires_in'] + time.time()),
            })
            provider.save(update_fields=['config'])
            self.providerconfig = provider.config
            return True, None
        return False, r.text

    def check_messaging_config(self, state):
        tokenexpires = timezone.make_aware(datetime.fromtimestamp(self.providerconfig.get('token_expires')))
        refreshtokenexpires = timezone.make_aware(datetime.fromtimestamp(self.providerconfig.get('refresh_token_expires')))

        if tokenexpires < timezone.now() + timedelta(days=10):
            # We start trying to refresh when there are 10 days to go
            if refreshtokenexpires < timezone.now() + timedelta(days=1):
                # We add one day margin here
                return False, "Refresh token has expired, re-authentication needed."

            # Attempt to refresh
            ok, err = self.refresh_access_token()
            if ok:
                return True, "Access token refreshed, new token valid until {}.".format(timezone.make_aware(datetime.fromtimestamp(self.providerconfig.get('token_expires'))))
            else:
                return False, "Access token refresh failed: {}".format(err)

        if refreshtokenexpires < timezone.now() + timedelta(days=10):
            return True, "Refresh token will expire in {} (on {}), manual re-authentication needed!".format(
                timeuntil(refresh_token_expires),
                refresh_token_expires,
            )

        # Token not expired or about to, so verify that what we have works.
        r = self._get(
            'rest/posts',
            params={
                'author': self.urn,
                'q': 'author',
                'count': 1,
            },
        )
        if r.status_code != 200:
            return False, "Failed to get post (sstatus {}): {}".format(r.status_code, r.text)
        # We can't really check that there is at least one post returned, because there might
        # be no posts available. But at least this way we have verified that the token is OK.
        return True, ''

    def get_link(self, id):
        return [
            'linkedin',
            'https://www.linkedin.com/feed/update/{}/'.format(post.statusid),
        ]
