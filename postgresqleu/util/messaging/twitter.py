from django.core.validators import ValidationError
from django.http import HttpResponse
from django import forms
from django.conf import settings
from django.contrib import messages
from django.db import transaction
import django.utils.timezone

import requests_oauthlib
from datetime import datetime
import dateutil.parser
import hmac
import hashlib
import json
import base64
import time

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.forms import LinkForCodeField
from postgresqleu.util.oauthapps import get_oauth_client, get_oauth_secret
from postgresqleu.util.messaging import re_token, get_messaging
from postgresqleu.util.messaging.util import send_reg_direct_message
from postgresqleu.util.messaging.common import store_incoming_post
from postgresqleu.util.validators import TwitterValidator

from postgresqleu.confreg.models import ConferenceRegistration, MessagingProvider, IncomingDirectMessage
from postgresqleu.confreg.models import ConferenceTweetQueue
from postgresqleu.confreg.backendforms import BackendSeriesMessagingForm

from .common import register_messaging_config

import logging
log = logging.getLogger(__name__)

_cached_twitter_users = {}


class TwitterBackendForm(BackendSeriesMessagingForm):
    initialconfig = LinkForCodeField(label='Get PIN code')
    twitterinfo = forms.CharField(widget=StaticTextWidget, label="Account information", required=False)
    webhookenabler = SubmitButtonField(label="Enable webhook", required=False)

    def fix_fields(self):
        super().fix_fields()

        if self.instance.config.get('token', None):
            del self.fields['initialconfig']
            self.config_fields = ['twitterinfo', 'webhookenabler']
            if 'webhook' in self.instance.config:
                self.fields['webhookenabler'].label = 'Disable webhook'
                self.fields['webhookenabler'].widget.label = 'Disable webhook'
                self.fields['webhookenabler'].callback = self.disable_webhook
            else:
                self.fields['webhookenabler'].callback = self.enable_webhook
            self.config_fieldsets = [
                {'id': 'twitter', 'legend': 'Twitter', 'fields': self.config_fields},
            ]
            self.config_readonly_fields = ['twitterinfo', ]

            if 'screen_name' not in self.instance.config or 'accountid' not in self.instance.config:
                try:
                    ai = Twitter(self.instance.id, self.instance.config).get_account_info()
                    self.instance.config.update(ai)
                    self.instance.save(update_fields=['config'])
                except Exception as e:
                    self.initial['twitterinfo'] = "Unable to fetch twitter account info: {}".format(e)
                    return

            self.initial.update({
                'twitterinfo': "Connected to twitter account @{}.".format(self.instance.config.get('screen_name', '*unknown*')),
            })
        else:
            # Not configured yet, so prepare for it!
            del self.fields['twitterinfo']
            del self.fields['webhookenabler']
            self.config_fields = ['initialconfig', ]
            self.config_fieldsets = [
                {'id': 'twitter', 'legend': 'Twitter', 'fields': ['initialconfig', ]},
            ]
            self.nosave_fields = ['initialconfig', ]

            # Ugly power-grab here, but let's see what's in our POST
            if self.request.POST.get('initialconfig', None):
                # Token is included, so don't try to get a new one
                self.fields['initialconfig'].widget.authurl = self.request.session['authurl']
            else:
                # Prepare the twitter setup
                try:
                    (auth_url, ownerkey, ownersecret) = TwitterSetup.get_authorization_data()
                    self.request.session['ownerkey'] = ownerkey
                    self.request.session['ownersecret'] = ownersecret
                    self.request.session['authurl'] = auth_url

                    self.fields['initialconfig'].widget.authurl = auth_url
                except Exception as e:
                    messages.error(self.request, 'Failed to initialize setup with Twitter: {}'.format(e))
                    del self.fields['initialconfig']
                    self.config_fields = []
                    self.config_fieldsets = []

    def clean(self):
        d = super().clean()
        if d.get('initialconfig', None):
            # We have received an initial config, so try to attach ourselves to twitter.
            try:
                tokens = TwitterSetup.authorize(self.request.session['ownerkey'],
                                                self.request.session['ownersecret'],
                                                d.get('initialconfig'),
                )
                self.instance.config['token'] = tokens.get('oauth_token')
                self.instance.config['secret'] = tokens.get('oauth_token_secret')
                del self.request.session['authurl']
                del self.request.session['ownerkey']
                del self.request.session['ownersecret']
                self.request.session.modified = True

                ai = Twitter(self.instance.id, self.instance.config).get_account_info()
                if MessagingProvider.objects.filter(
                        classname='postgresqleu.util.messaging.twitter.Twitter',
                        config__accountid=ai['accountid'],
                        series__isnull=True,
                ).exclude(pk=self.instance.pk).exists():
                    raise Exception("Another messaging provider is already configured for this Twitter account")
                self.instance.config.update(ai)
            except Exception as e:
                self.add_error('initialconfig', 'Could not set up Twitter: {}'.format(e))
                self.add_error('initialconfig', 'You probably have to restart the process')
        elif 'twitterinfo' not in d:
            raise ValidationError("Twitter information is incomplete")
        return d

    # Webhooks are global to our client, but we have to turn on and off the individual
    # subscriptions to the webhooks. If no webhook is configured, we will automtaically
    # set it up when the first subscription should be added.
    def enable_webhook(self, request):
        t = Twitter(self.instance.id, self.instance.config)
        try:
            res, env, msg = t.check_global_webhook()
            if not res:
                messages.error(request, msg)
                return

            if msg:
                messages.info(request, msg)

            # Now subscribe to this webhook
            r = t.tw.post('https://api.twitter.com/1.1/account_activity/all/{}/subscriptions.json'.format(env), params={
            })
            if r.status_code != 204:
                r.raise_for_status()
                messages.error(request, "Error registering subscription, status code {}".format(r.status_code))
                return

            # Else we are registered and have a subscription!
            self.instance.config['webhook'] = {
                'ok': 1,
            }
            self.instance.save(update_fields=['config'])
            messages.info(request, "Subscribed to webhook")
        except Exception as e:
            messages.error(request, "Error registering twitter webhook/subscription: {}".format(e))

    def disable_webhook(self, request):
        t = Twitter(self.instance.id, self.instance.config)
        try:
            r = t.tw.delete('https://api.twitter.com/1.1/account_activity/all/pgeu/subscriptions.json')
            if r.status_code != 204:
                jj = r.json()
                if 'errors' not in jj:
                    messages.error(request, "Error removing subscription, status {}".format(r.status_ocode))
                    return
                # Code 34 means this subscription didn't exist in the first place, so treat it
                # as if we removed it.
                if jj['errors'][0]['code'] != 34:
                    messages.error(request, "Error removing subscription: {}".format(jj['errors'][0]['message']))
                    return
            del self.instance.config['webhook']
            self.instance.save(update_fields=['config'])
            messages.info(request, "Webhook has been disabled!")
        except Exception as e:
            messages.error(request, "Error removing subscription: {}".format(e))


class Twitter(object):
    provider_form_class = TwitterBackendForm
    can_process_incoming = False  # Temporarily(?) disabled due to paid API tiers
    can_broadcast = True
    can_notification = False  # Temporarily(?) disabled due to paid API tiers
    direct_message_max_length = None
    typename = 'Twitter'
    max_post_length = 280

    @classmethod
    def can_track_users_for(self, whatfor):
        return True

    @classmethod
    def validate_baseurl(self, baseurl):
        return None

    @classmethod
    def clean_identifier_form_value(self, whatfor, value):
        # Always add the @ at the beginning. The validator forcibly strips it
        # so for backwards compatibility as long as that validator is used elsewhere,
        # we add it back here.
        return '@{}'.format(TwitterValidator(value))

    @classmethod
    def get_link_from_identifier(self, value):
        return 'https://twitter.com/{}'.format(value.lstrip('@'))

    def __init__(self, id, config):
        self.providerid = id
        self.providerconfig = config
        self._tw = None

    @property
    def tw(self):
        if not self._tw and 'token' in self.providerconfig:
            self._tw = requests_oauthlib.OAuth1Session(
                get_oauth_client('https://api.twitter.com'),
                get_oauth_secret('https://api.twitter.com'),
                self.providerconfig['token'],
                self.providerconfig['secret'],
            )
        return self._tw

    def get_account_info(self):
        r = self.tw.get('https://api.twitter.com/1.1/account/verify_credentials.json?include_entities=false&skip_status=true&include_email=false', timeout=30)
        if r.status_code != 200:
            raise Exception("http status {}".format(r.status_code))
        j = r.json()
        return {
            'screen_name': j['screen_name'],
            'accountid': j['id'],
        }

    def post(self, tweet, image=None, replytotweetid=None):
        d = {
            'text': tweet,
        }
        if replytotweetid:
            raise Exception("No v2 support for replies yet - need paid account")
            d['in_reply_to_status_id'] = replytotweetid
            d['auto_populate_reply_metadata'] = True

        if image:
            # Images are separately uploaded as a first step
            r = self.tw.post('https://upload.twitter.com/1.1/media/upload.json', files={
                'media': bytearray(image),
            }, timeout=30)
            if r.status_code != 200:
                return (None, 'Media upload: {}'.format(r.text))
            d['media'] = {
                'media_ids': [str(r.json()['media_id']), ]
            }

        while d['text']:
            r = self.tw.post('https://api.twitter.com/2/tweets', json=d, timeout=30)
            if r.status_code == 201:
                return (r.json()['data']['id'], None)
            else:
                # Normally Twitter gives us a json result on errors as well, so let's try that first
                try:
                    errj = r.json()
                    if errj['errors'][0]['code'] == 186:
                        # Code for "tweet too long", so we try to truncate it a bit and try again.
                        # We truncate by taking one word off at a time and hope that's enough.
                        # (yes this is ugly, but figuring out exactly how twitter counts the length
                        # of a tweet without documentation turns out to be very hard).
                        pieces = d['status'].rsplit(None, 1)
                        if len(pieces) > 1:
                            # If two pieces it means we managed to truncate it, so we try again
                            d['status'] = pieces[0]

                            # Sleep before we try again, but hopefully 1 second is enough here.
                            time.sleep(1)
                            continue
                        else:
                            return (None, "Unable to truncate tweet further, only a single word and Twitter still returns 186!")
                    else:
                        return (None, r.text)
                except Exception as e:
                    return (None, "{}\n\nContent was:\n{}".format(str(e), r.text))

    def repost(self, tweetid):
        raise Exception("No v2 support for reposts yet - need paid account")
        r = self.tw.post('https://api.twitter.com/1.1/statuses/retweet/{0}.json'.format(tweetid), timeout=30)
        if r.status_code != 200:
            # If the error is "you have already retweeted this", we just ignore it
            try:
                if r.json()['errors'][0]['code'] == 327:
                    return (True, None)
            except Exception:
                pass
            return (None, r.text)
        return (True, None)

    def send_direct_message(self, recipient_config, msg):
        raise Exception("No v2 support for DMs yet - need paid account")
        r = self.tw.post('https://api.twitter.com/1.1/direct_messages/events/new.json', json={
            'event': {
                'type': 'message_create',
                'message_create': {
                    'target': {
                        'recipient_id': recipient_config['twitterid'],
                    },
                    'message_data': {
                        'text': msg,
                    }
                }
            }
        }, timeout=30)

        if r.status_code != 200:
            try:
                # Normally these errors come back as json, so try to return that
                ej = r.json()['errors'][0]
                raise Exception('{}: {}'.format(ej['code'], ej['message']))
            except Exception as e:
                r.raise_for_status()

    def poll_public_posts(self, lastpoll, checkpoint):
        raise Exception("No v2 support for polling yet - need paid account")
        if checkpoint:
            sincestr = "&since_id={}".format(checkpoint)
        else:
            sincestr = ""
        r = self.tw.get('https://api.twitter.com/1.1/statuses/mentions_timeline.json?tweet_mode=extended{}'.format(sincestr), timeout=30)
        r.raise_for_status()
        for tj in r.json():
            # If this is somebody retweeting one of our outgoing tweets we don't want to include
            # it as an incoming, but every thing else counts.
            if not tj.get('self_retweet', False):
                yield self._parse_tweet_struct(tj)

    def _parse_tweet_struct(self, tj):
        d = {
            'id': int(tj['id']),
            'datetime': dateutil.parser.parse(tj['created_at']),
            'text': tj.get('full_text', tj.get('text')),
            'replytoid': tj['in_reply_to_status_id'] and int(tj['in_reply_to_status_id']) or None,
            'author': {
                'name': tj['user']['name'],
                'username': tj['user']['screen_name'],
                'id': int(tj['user']['id']),
                'imageurl': tj['user']['profile_image_url_https'],
            },
            'media': [m['media_url_https'] for m in tj['entities'].get('media', [])],
        }
        if tj['is_quote_status'] and 'quoted_status_id' in tj:
            d['quoted'] = {
                'id': int(tj['quoted_status_id']),
                'text': tj['quoted_status'].get('full_text', tj['quoted_status'].get('text', '')),
                'permalink': tj['quoted_status_permalink'],
            }

        # Check if this is a retweet of something we posted
        if 'retweeted_status' in tj:
            d['self_retweet'] = ConferenceTweetQueue.objects.filter(postids__contains={tj['retweeted_status']['id']: self.providerid}).exists()
        else:
            d['self_retweet'] = False
        return d

    # This is delivered by the webhook if it's enabled
    def poll_incoming_private_messages(self, lastpoll, checkpoint):
        raise Exception("No v2 support for private messages yet - need paid account")
        # Ugh. Seems twitter always delivers the last 30 days. So we need to do some manual
        # checking and possibly page backwards. At least it seems they are coming back in
        # reverse chronological order (which is not documented)
        highdt = lastpoll
        cursor = None
        while True:
            p = {
                'count': 50,
            }
            if cursor:
                p['cursor'] = cursor

            r = self.tw.get('https://api.twitter.com/1.1/direct_messages/events/list.json', params=p, timeout=30)
            r.raise_for_status()

            j = r.json()

            for e in j['events']:
                dt = datetime.fromtimestamp(int(e['created_timestamp']) / 1000, tz=django.utils.timezone.utc)
                if dt < lastpoll:
                    break
                highdt = max(dt, highdt)
                if e['type'] == 'message_create':
                    self.process_incoming_message_create_struct(e['id'], dt, e['message_create'])

            # Consumed all entries. Do we have a cursor for the next one
            if 'next_cursor' in j:
                cursor = j['next_cursor']
                continue
            else:
                # No cursor, and we've consumed all, so we're done
                break
        return highdt, 0

    def process_incoming_message_create_struct(self, idstr, dt, m):
        if int(m['sender_id']) != int(self.providerconfig['accountid']):
            # We ignore messages from ourselves
            msgid = int(idstr)
            if IncomingDirectMessage.objects.filter(provider_id=self.providerid, postid=msgid).exists():
                # We've already seen this one
                return

            dm = IncomingDirectMessage(
                provider_id=self.providerid,
                postid=msgid,
                time=dt,
                sender={
                    'id': int(m['sender_id']),
                },
                txt=m['message_data']['text'],
            )
            self.process_incoming_dm(dm)
            dm.save()

    _screen_names = {}

    def get_user_screen_name(self, uid):
        if uid not in self._screen_names:
            r = self.tw.get('https://api.twitter.com/1.1/users/show.json', params={'user_id': uid}, timeout=30)
            r.raise_for_status()
            self._screen_names[uid] = r.json()['screen_name']
        return self._screen_names[uid]

    def process_incoming_dm(self, dm):
        if register_messaging_config(dm, self):
            self.send_read_receipt(dm.sender['id'], dm.postid)

    def get_regconfig_from_dm(self, dm):
        # Return a structure to store in messaging_config corresponding to the dm

        # We get the screen_name so we can be friendly to the user! And when we've
        # done that, we might as well cache it in the message info.
        dm.sender['name'] = self.get_user_screen_name(dm.sender['id'])
        return {
            'twitterid': dm.sender['id'],
            'screen_name': dm.sender['name'],
        }

    def get_regdisplayname_from_config(self, config):
        return config.get('screen_name', '<unspecified>')

    def process_incoming_tweet_create_event(self, mp, tce):
        d = self._parse_tweet_struct(tce)

        # If this is somebody retweeting one of our outgoing tweets we don't want to include
        # it as an incoming, but every thing else counts.
        if not d.get('self_retweet', False):
            store_incoming_post(mp, d)

    def get_public_url(self, post):
        return 'https://twitter.com/{}/status/{}'.format(post.author_screenname, post.statusid)

    def get_attendee_string(self, token, messaging, attendeeconfig):
        if 'screen_name' in attendeeconfig:
            return "Your notifications will be sent to @{}.".format(attendeeconfig['screen_name']), None
        else:
            return 'twitter_invite.html', {
                'twittername': self.providerconfig['screen_name'],
                'twitterid': self.providerconfig['accountid'],
                'token': token,
            }

    def send_read_receipt(self, recipient, maxval):
        r = self.tw.post('https://api.twitter.com/1.1/direct_messages/mark_read.json', params={
            'last_read_event_id': maxval,
            'recipient_id': recipient,
        }, timeout=30)
        # Ignore errors

    def check_messaging_config(self, state):
        # Check that we can get our own account info
        try:
            self.get_account_info()
        except Exception as e:
            return False, 'Could not get own account information: {}'.format(e)

        # If we have a webhook configured, make sure it's still live
        if 'webhook' in self.providerconfig:
            retmsg = ''
            if 'global_webhook_checked' not in state:
                res, env, msg = self.check_global_webhook()
                if not res:
                    # If we failed to check the global webhook, it's now time to give up
                    return False, msg
                state['env'] = env
                state['global_webhook_checked'] = True
                if msg:
                    retmsg += msg + "\n"
            else:
                env = state['env']

            # Global webhook has been abled by this or previous run. Now check our subscription.
            r = self.tw.get('https://api.twitter.com/1.1/account_activity/all/{}/subscriptions.json'.format(env), timeout=30)
            if r.status_code == 204:
                # We are subscribed!
                return True, retmsg

            # Attempt to re-subscribe
            r = self.tw.post('https://api.twitter.com/1.1/account_activity/all/{}/subscriptions.json'.format(env), params={}, timeout=30)
            if r.status_code == 204:
                return True, retmsg + 'Resubscribed user to webhook.'

            return False, retmsg + 'Unable to resubscribe to webhook: {}'.format(r.status_code)

            # 204 means we were resubecribed
            return True, retmsg

        # Webhook not configured, so everything is always good
        return True, ''

    def check_global_webhook(self):
        # Check if the global webhook is here, and enabled!
        r = self.tw.get('https://api.twitter.com/1.1/account_activity/all/webhooks.json', timeout=30)
        r.raise_for_status()
        j = r.json()

        if len(j['environments']) == 0:
            return False, None, "No environments found to enable webhook"
        elif len(j['environments']) > 1:
            return False, None, "More than one environment found to enable webhook, not supported"
        env = j['environments'][0]['environment_name']

        webhookurl = "{}/wh/twitter/".format(settings.SITEBASE)

        for wh in j['environments'][0]['webhooks']:
            if wh['url'] == webhookurl:
                # Webhook is already configured! Is it valid?
                if not wh['valid']:
                    # Re-enable the webhook
                    r = self.tw.put('https://api.twitter.com/1.1/account_activity/all/{}/webhooks/{}.json'.format(
                        env,
                        wh['id'],
                    ), timeout=30)
                    if r.status_code != 204:
                        return False, None, "Webhook marked invalid, and was unable to re-enable!"
                    else:
                        return True, env, "Webhook was marked invalid. Has now been re-enabled."

                return True, env, ""

        # No matching webhook for us, so we go create it
        r = self.tw.post('https://api.twitter.com/1.1/account_activity/all/{}/webhooks.json'.format(env), params={
            'url': webhookurl,
        }, timeout=30)
        jj = r.json()
        if 'errors' in jj:
            return False, None, "Error registering twitter webhook: {}".format(jj['errors'][0]['message'])
        r.raise_for_status()
        return True, env, "Global webhook has been registered"

    def get_link(self, id):
        return [
            'twitter',
            'https://twitter.com/{}/status/{}'.format(
                self.providerconfig.get('screen_name', ''),
                id,
            )
        ]


class TwitterSetup(object):
    @classmethod
    def get_authorization_data(self):
        oauth = requests_oauthlib.OAuth1Session(get_oauth_client('https://api.twitter.com'), get_oauth_secret('https://api.twitter.com'), callback_uri='oob')
        fetch_response = oauth.fetch_request_token('https://api.twitter.com/oauth/request_token')
        auth_url = oauth.authorization_url('https://api.twitter.com/oauth/authorize')

        return (auth_url,
                fetch_response.get('oauth_token'),
                fetch_response.get('oauth_token_secret'),
        )

    @classmethod
    def authorize(self, ownerkey, ownersecret, pincode):
        oauth = requests_oauthlib.OAuth1Session(get_oauth_client('https://api.twitter.com'),
                                                get_oauth_secret('https://api.twitter.com'),
                                                resource_owner_key=ownerkey,
                                                resource_owner_secret=ownersecret,
                                                verifier=pincode)
        tokens = oauth.fetch_access_token('https://api.twitter.com/oauth/access_token')

        return tokens


# Twitter needs a special webhook URL since it's global and not per provider
def process_twitter_webhook(request):
    # No support for the V2 stuff yet as it needs a paid account. So just accept
    # the webhooks without doing anything.
    return HttpResponse("OK")

    if 'crc_token' in request.GET:
        # This is a pingback from twitter to see if we are alive
        d = hmac.new(
            bytes(get_oauth_secret('https://api.twitter.com'), 'utf-8'),
            msg=bytes(request.GET['crc_token'], 'utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return HttpResponse(json.dumps({
            'response_token': 'sha256={}'.format(base64.b64encode(d).decode('utf8')),
        }), content_type='application/json')

    # Validate the signature
    if 'HTTP_X_TWITTER_WEBHOOKS_SIGNATURE' not in request.META:
        print("Twitter webhooks signature missing")
        return HttpResponse('Webhooks signature missing', status=400)

    if not request.META['HTTP_X_TWITTER_WEBHOOKS_SIGNATURE'].startswith('sha256='):
        print("Invalid signature, not starting with sha256=: {}".format(request.META['HTTP_X_TWITTER_WEBHOOKS_SIGNATURE']))
        return HttpResponse('Webhooks signature starts incorrectly', status=400)

    sig = base64.b64decode(request.META['HTTP_X_TWITTER_WEBHOOKS_SIGNATURE'][7:])
    d = hmac.new(
        bytes(get_oauth_secret('https://api.twitter.com'), 'utf-8'),
        msg=request.body,
        digestmod=hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(sig, d):
        return HttpResponse('Webhooks signature is wrong', status=400)

    # Load and parse the hook message
    j = json.loads(request.body.decode('utf-8'))

    _cached_messaging = {}

    def _get_messaging_from_uid(uid):
        if uid not in _cached_messaging:
            try:
                mp = MessagingProvider.objects.get(
                    classname='postgresqleu.util.messaging.twitter.Twitter',
                    config__accountid=uid,
                    series__isnull=False,
                )
                _cached_messaging[uid] = (mp, get_messaging(mp))
            except MessagingProvider.DoesNotExist:
                return None, None
        return _cached_messaging[uid]

    for dme in j.get('direct_message_events', []):
        with transaction.atomic():
            if 'message_create' in dme:
                # Incoming direct message
                recipient = int(dme['message_create']['target']['recipient_id'])
                sender = int(dme['message_create']['sender_id'])
                mp, tw = _get_messaging_from_uid(recipient)
                if tw:
                    dt = datetime.fromtimestamp(int(dme['created_timestamp']) / 1000, tz=django.utils.timezone.utc)
                    tw.process_incoming_message_create_struct(dme['id'], dt, dme['message_create'])
                else:
                    log.error("Could not find provider for direct message event: {}".format(dme))

    for tce in j.get('tweet_create_events', []):
        with transaction.atomic():
            recipient = int(j['for_user_id'])
            mp, tw = _get_messaging_from_uid(recipient)
            if mp:
                tw.process_incoming_tweet_create_event(mp, tce)
            else:
                log.error("Could not find provider for incoming tweet: {}".format(j))

    return HttpResponse("OK")
