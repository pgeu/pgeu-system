from django import forms
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.conf import settings
import django.utils.timezone

import base64
import io
import json
import re
import requests
from datetime import datetime

from postgresqleu.util.random import generate_random_token
from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.messaging import re_token
from postgresqleu.util.messaging.util import notify_twitter_moderation

from postgresqleu.confreg.backendforms import BackendSeriesMessagingForm
from postgresqleu.confreg.models import ConferenceMessaging, ConferenceRegistration, IncomingDirectMessage
from postgresqleu.confreg.models import ConferenceTweetQueue
from postgresqleu.scheduler.util import trigger_immediate_job_run

from .util import send_reg_direct_message, send_channel_message
from .common import register_messaging_config

import logging
log = logging.getLogger(__name__)


class TelegramBackendForm(BackendSeriesMessagingForm):
    telegramtoken = forms.CharField(required=True, label="Telegram token",
                                    widget=forms.widgets.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
                                    help_text='Create a new bot in the Telegram Botfather, and copy/paste the access token here')
    telegramstatus = forms.CharField(widget=StaticTextWidget, label="Telegram information", required=False)
    webhookenabler = SubmitButtonField(label="Enable webhook", required=False)

    exclude_fields_from_validation = ['telegramstatus', 'webhookenabler', ]

    @property
    def config_fields(self):
        f = ['telegramtoken', ]
        if self.instance.config.get('telegramtoken', None):
            f.extend(['telegramstatus', 'webhookenabler'])
        return f

    @property
    def config_fieldsets(self):
        return [
            {'id': 'telegram', 'legend': 'Telegram', 'fields': self.config_fields},
        ]

    def fix_fields(self):
        super().fix_fields()
        if self.instance.config.get('telegramtoken', None):
            # Existing token, make a call to telegram to see what's up, if necessary
            try:
                if 'botname' not in self.instance.config:
                    tgm = Telegram(self.instance.id, self.instance.config)
                    botinfo = tgm.get('getMe')
                    self.instance.config.update({
                        'botname': botinfo['username'],
                        'botfullname': botinfo['first_name'],
                    })
                    self.instance.save(update_fields=['config'])
                self.initial['telegramstatus'] = 'Telegram bot username {}, full name "{}", connected.'.format(
                    self.instance.config['botname'],
                    self.instance.config['botfullname'],
                )
            except Exception as e:
                self.initial['telegramstatus'] = 'Failed to get Telegram info: {}'.format(e)

            # Is the webhook enabled?
            if 'webhook' in self.instance.config:
                # It is!
                self.fields['webhookenabler'].label = 'Disable webhook'
                self.fields['webhookenabler'].widget.label = 'Disable webhook'
                self.fields['webhookenabler'].callback = self.disable_webhook
            else:
                self.fields['webhookenabler'].callback = self.enable_webhook
        else:
            self.remove_field('telegramstatus')
            self.remove_field('webhookenabler')

    def enable_webhook(self, request):
        token = generate_random_token()

        Telegram(self.instance.id, self.instance.config).post('setWebhook', {
            'url': '{}/wh/{}/{}/'.format(settings.SITEBASE, self.instance.id, token),
            'max_connections': 2,
            'allowed_updates': ['channel_post', 'message'],
        })
        self.instance.config['webhook'] = {
            'token': token,
        }
        self.instance.save(update_fields=['config'])

        messages.info(request, "Webhook has been enabled!")
        return True

    def disable_webhook(self, request):
        Telegram(self.instance.id, self.instance.config).post('deleteWebhook')

        del self.instance.config['webhook']
        self.instance.save(update_fields=['config'])

        messages.info(request, "Webhook has been disabled!")
        return True


class Telegram(object):
    provider_form_class = TelegramBackendForm
    can_privatebcast = True
    can_notification = True
    can_orgnotification = True
    can_socialmediamanagement = True
    direct_message_max_length = None
    typename = 'Telegram'

    @classmethod
    def validate_baseurl(self, baseurl):
        return None

    def __init__(self, id, config):
        self.providerid = id
        self.providerconfig = config

    def refresh_messaging_config(self, config):
        mod = False

        if 'channeltoken' not in config:
            config['channeltoken'] = {}
        if 'tokenchannel' not in config:
            config['tokenchannel'] = {}

        for channel in ['privatebcast', 'orgnotification', 'socialmediamanagement']:
            if channel not in config['channeltoken']:
                # Create a token!
                t = generate_random_token()
                config['channeltoken'][channel] = t
                config['tokenchannel'][t] = channel
            mod = True
        return mod

    def get_channel_field(self, instance, fieldname):
        commontxt = "<br/><br/>To set or edit this, please invite the bot @{} to the selected channel as an administrator, and after that's done, paste the token {} in the channel to associated. Then wait a bit and refresh this page (you will also be notified in the channel).".format(self.providerconfig['botname'], instance.config['channeltoken'][fieldname])
        if 'channels' in instance.config and fieldname in instance.config['channels']:
            txt = 'Configured to talk in channel with id {} and title "{}".'.format(
                instance.config['channels'][fieldname]['id'],
                instance.config['channels'][fieldname]['title'],
            )
            return SubmitButtonField(label='Disable channel', prefixparagraph=txt + commontxt, callback=self.disable_channel(instance, fieldname))
        else:
            txt = '<strong>Not currently attached to a channel!</strong>'
            return forms.CharField(widget=StaticTextWidget, initial=txt + commontxt)

    def disable_channel(self, instance, channelname):
        def _disable_channel(request):
            del instance.config['channels'][channelname]
            instance.save(update_fields=['config', ])
        return _disable_channel

    def get(self, method, params={}):
        r = requests.get(
            'https://api.telegram.org/bot{}/{}'.format(self.providerconfig['telegramtoken'], method),
            params=params,
            timeout=10
        )
        r.raise_for_status()
        j = r.json()
        if not j['ok']:
            raise Exception("OK was {}".format(j['ok']))
        return j['result']

    def post(self, method, params={}, ignoreerrors=False, files=None):
        r = requests.post(
            'https://api.telegram.org/bot{}/{}'.format(self.providerconfig['telegramtoken'], method),
            data=params,
            files=files,
            timeout=10
        )
        if ignoreerrors:
            return None

        r.raise_for_status()
        j = r.json()
        if not j['ok']:
            raise Exception("OK was {}".format(j['ok']))
        return j['result']

    def send_direct_message(self, recipient_config, msg):
        self.post('sendMessage', {
            'chat_id': recipient_config['userid'],
            'text': msg,
        })

    def post_channel_message(self, messaging, channelname, msg):
        if channelname == '__telegram_internal':
            # This is a telegram-to-telegram message, which means the message is actually a
            # json blob telling us what to do. In this case we blindly trust it since it
            # came from the same module, and just relay it over to Telegram.
            struct = json.loads(msg)
            msg = self.post(
                struct['command'],
                struct['param'],
                files={k: io.BytesIO(base64.b64decode(v)) for k, v in struct['files'].items()} if struct.get('files', None) else None,
                ignoreerrors=struct.get('ignoreerrors', False)
            )

            # Not-so-generic functionality to store the messageid on a queued tweet
            # if requested.
            if struct.get('store_messageid_on_tweet', None):
                try:
                    tweet = ConferenceTweetQueue.objects.get(pk=struct['store_messageid_on_tweet'])
                    if 'telegram' not in tweet.metadata:
                        tweet.metadata['telegram'] = {}
                    tweet.metadata['telegram'][str(messaging.id)] = {'moderator': msg['message_id']}
                    tweet.save(update_fields=['metadata', ])
                except ConferenceTweetQueue.DoesNotExist:
                    # Ignore if it's for some reason gone
                    pass

        elif channelname not in messaging.config.get('channels', {}):
            # Don't crash when there is no channel configured, instead just ignore the message
            print("Channel {} not found in provider {}, dropping message", messaging.config.get('botname', '*unnamed bot*'))
            return
        else:
            self.post('sendMessage', {
                'chat_id': messaging.config['channels'][channelname]['id'],
                'text': msg,
            })

    def poll_incoming_private_messages(self, lastpoll, checkpoint):
        # If we are configured with a webhook, telegram will return an error if
        # we try to get the data this way as well, so don't try that.
        if 'webhook' in self.providerconfig:
            return lastpoll, checkpoint

        # We'll get up to 100 updates per run, which is the default
        res = self.get('getUpdates', {
            'offset': checkpoint + 1,
            'allowed_updates': ['channel_post', 'message', 'callback_query'],
        })

        # For now we don't store telegram input, we just do automated processing to figure
        # out if we're connected to something.
        for u in res:
            if 'callback_query' in u:
                self.process_callback_query(u['callback_query'])
            elif 'channel_post' in u:
                self.process_channel_post(u['channel_post'])
            elif 'message' in u:
                self.process_incoming_chat_structure(u)

        if res:
            return timezone.now(), max((u['update_id'] for u in res))
        else:
            return timezone.now(), checkpoint

    def process_webhook(self, request):
        body = request.body.decode('utf8', errors='ignore')
        try:
            j = json.loads(body)
            if 'callback_query' in j:
                self.process_callback_query(j['callback_query'])
            elif 'channel_post' in j:
                self.process_channel_post(j['channel_post'])
            elif 'message' in j:
                self.process_incoming_chat_structure(j)
            # All other types we just ignore for now
            return HttpResponse("OK")
        except Exception as e:
            log.error("Exception processing Telegram webhook: {}".format(e))
            log.error("Telegram data was: {}".format(body))
            return HttpResponse("Internal error", status=500)

    def process_channel_post(self, p):
        if 'text' not in p:
            # This is some kind of channel post that is not text, so we just
            # ignore it.
            return

        # Does it look like a token? If so, try to attach this channel
        for m in re_token.findall(p['text']):
            if self.process_token_match(m, p):
                return

    def process_token_match(self, m, p):
        # Found a match.
        # Now try to find if this is an actual token, and assign the channel
        # as required.
        try:
            r = ConferenceMessaging.objects.get(
                provider_id=self.providerid,
                config__tokenchannel__has_key=m
            )
            chan = r.config['tokenchannel'][m]
            hadprevchannel = 'channels' in r.config and chan in r.config['channels']
            if 'channels' not in r.config:
                r.config['channels'] = {}

            # Export a channel invite link, so that we have one
            self.post('exportChatInviteLink', {'chat_id': p['chat']['id']}, ignoreerrors=True)
            chatobj = self.get('getChat', {'chat_id': p['chat']['id']})
            r.config['channels'][chan] = {
                'id': p['chat']['id'],
                'title': p['chat']['title'],
                'invitelink': chatobj.get('invite_link', None),
            }
            r.save(update_fields=['config'])
            try:
                # Ignore if this fails, probably permissions
                self.post('deleteMessage', {
                    'chat_id': p['chat']['id'],
                    'message_id': p['message_id']
                })
            except Exception as e:
                pass

            # Send a reply, and this should not fail
            send_channel_message(r, chan,
                                 'Thank you, this channel has now been associated with {} channel {}'.format(
                                     r.conference.conferencename,
                                     chan
                                 ))
            if hadprevchannel:
                send_channel_message(r, chan, 'The previously existing channel association has been removed.')

        except ConferenceMessaging.DoesNotExist:
            # Just ignore it, since it wasn't an active token.
            pass

    def process_incoming_chat_structure(self, u):
        # We can get messages for things that aren't actually messages, such as "you're invited to
        # a channel".
        if 'text' not in u['message']:
            return

        msgid = int(u['update_id'])
        if IncomingDirectMessage.objects.filter(provider_id=self.providerid, postid=msgid).exists():
            # We've already seen this one
            return

        # Does it look like a token? If so, try to attach to this channel
        for m in re_token.findall(u['message']['text']):
            if self.process_token_match(m, u['message']):
                return

        # If the message has no sender, we're going to ignore it. This could for
        # exaple be an automatically forwarded message internally in Telegram.
        if 'id' not in u['message']['from']:
            return

        # Some users don't have usernames. In those cases, fake it from the id, since we
        # want the username for nicer messages.
        if 'username' not in u['message']['from']:
            u['message']['from']['username'] = 'id:{}'.format(u['message']['from']['id'])

        # Else it's a regular message, so store it.

        msg = IncomingDirectMessage(
            provider_id=self.providerid,
            postid=msgid,
            time=datetime.fromtimestamp(int(u['message']['date']), tz=django.utils.timezone.utc),
            sender={
                'username': u['message']['from']['username'],
                'userid': u['message']['from']['id'],
            },
            txt=u['message']['text'],
        )
        self.process_incoming_chat_message(msg)
        msg.save()

    def process_incoming_chat_message(self, msg):
        register_messaging_config(msg, self)

    def get_regconfig_from_dm(self, dm):
        # Return a structure to store in messaging_config corresponding to the dm
        return dm.sender

    def get_regdisplayname_from_config(self, config):
        return config.get('username', '<unspecified>')

    def get_attendee_string(self, token, messaging, attendeeconfig):
        if 'userid' in attendeeconfig:
            return 'telegram_ready.html', {
                'username': attendeeconfig['username'],
                'invitelink': messaging.config.get('channels', {}).get('privatebcast', {}).get('invitelink', None),
            }
        else:
            return 'telegram_invite.html', {
                'botname': self.providerconfig['botname'],
                'token': token,
            }

    def check_messaging_config(self, state):
        if 'webhook' in self.providerconfig:
            token = self.providerconfig['webhook']['token']

            webhookurl = '{}/wh/{}/{}/'.format(settings.SITEBASE, self.providerid, token)

            whi = self.get('getWebhookInfo')
            if whi['url'] != webhookurl:
                self.post('setWebhook', {
                    'url': webhookurl,
                    'max_connections': 2,
                    'allowed_updates': ['channel_post', 'message'],
                })
                return True, 'Webhook resubscribed'

        return True, ''

    def notify_twitter_moderation(self, messaging, tweet, completed, approved=False):
        if 'channels' not in messaging.config:
            # If we don't have any channels configure d*at all*, then there is definitely
            # nothing to do and we shouldn't crash.
            return
        if 'socialmediamanagement' not in messaging.config['channels']:
            # If we don't have a social media channel, then there is nothing to do!
            return

        chatid = messaging.config['channels']['socialmediamanagement']['id']
        text = "A new tweet has been posted and needs moderation:\n```\n{}\n```\nPost date: `{}`\nAuthor: `{}`\n".format(tweet.contents, tweet.datetime, tweet.author.username)

        if completed:
            # Moderation is completed, so edit the existing entry (if there is one) to
            # remove the buttons and indicate what happened.
            messageid = tweet.metadata.get('telegram', {}).get(str(messaging.id), {}).get('moderator', None)
            if messageid:
                text = text + "\n\nThis tweet has been `{}` by `{}`\n".format(
                    'approved' if approved else 'discarded',
                    tweet.approvedby.username,
                )
                send_channel_message(messaging, '__telegram_internal', json.dumps({
                    'command': 'editMessageCaption' if tweet.image else 'editMessageText',
                    'param': {
                        'chat_id': chatid,
                        'message_id': messageid,
                        'parse_mode': 'MarkdownV2',
                        'caption' if tweet.image else 'text': text,
                    },
                    'ignoreerrors': True,
                }))
                send_channel_message(messaging, '__telegram_internal', json.dumps({
                    'command': 'editMessageReplyMarkup',
                    'param': {
                        'chat_id': chatid,
                        'message_id': messageid,
                        'reply_markup': '',
                    },
                    'ignoreerrors': True,
                }))
        else:
            # Post an entry to the channel with buttons to moderate

            send_channel_message(messaging, '__telegram_internal', json.dumps({
                'command': 'sendPhoto' if tweet.image else 'sendMessage',
                'store_messageid_on_tweet': tweet.id,
                'param': {
                    'chat_id': chatid,
                    'caption' if tweet.image else 'text': text,
                    'parse_mode': 'MarkdownV2',
                    'reply_markup': json.dumps({
                        'inline_keyboard': [
                            [
                                {'text': 'Approve', 'callback_data': 'sm:{}:approve'.format(tweet.id)},
                                {'text': 'Discard', 'callback_data': 'sm:{}:discard'.format(tweet.id)},
                            ],
                        ],
                    }),
                },
                'files': {
                    'photo': base64.b64encode(tweet.image).decode(),
                } if tweet.image else None,
            }))

    def process_callback_query(self, cb):
        if 'data' not in cb:
            return

        m = re.match(r'^sm:(\d+):(approve|discard)$', cb['data'])
        if not m:
            return

        try:
            tweet = ConferenceTweetQueue.objects.get(pk=int(m.group(1)))
        except ConferenceTweetQueue.DoesNotExist:
            return

        # Identify which messaging we're part of here, going through the channel id
        # XXX: once we've migrated fully off postgres 11, replace with jsonpath:
        # config @? '$.channels.*.id ? (@ == <id>)'
        chatid = cb.get('message', {}).get('chat', {}).get('id', None)
        if not chatid:
            # No chat -> no process
            return

        messaging = None
        for _m in ConferenceMessaging.objects.only('config').filter(conference=tweet.conference, provider=self.providerid):
            for _cname, _cconf in _m.config.get('channels', {}).items():
                if int(_cconf.get('id', None)) == int(chatid):
                    messaging = _m
                    break
            if messaging:
                break
        else:
            # Could not find a messaging for this, so just ignore it
            return

        def _answer_with_alert(msg):
            send_channel_message(messaging, '__telegram_internal', json.dumps({
                'command': 'answerCallbackQuery',
                'param': {
                    'callback_query_id': cb['id'],
                    'text': msg,
                    'show_alert': True,
                }
            }))

        if tweet.approved:
            # Already approved, so ignore
            _answer_with_alert('Tweet has already been approved')
            return

        fromid = cb['from']['id']
        try:
            reg = ConferenceRegistration.objects.get(conference=tweet.conference, messaging_config__contains={'userid': int(fromid)})
            fromuser = reg.attendee
        except ConferenceRegistration.DoesNotExist:
            # let the user know that they need to register their account first
            _answer_with_alert('Could not determine your username. This most commonly means your Telegram account is not linked to your conference attendance on the Your Registration page of the website.')
            return

        if m.group(2) == 'approve' and fromuser == tweet.author:
            _answer_with_alert('You cannot approve your own tweet')
            return

        # Admins can always approve tweets, but volunteers can only do so if that's enabled
        if not reg.is_admin:
            if tweet.conference.twitter_postpolicy == 0:
                _answer_with_alert('Nobody is allowed to approve tweets')
                return
            if tweet.conference.twitter_postpolicy in (1, 2):
                _answer_with_alert('Only administrators can approve tweets')
                return
            if tweet.conference.twitter_postpolicy in (3, 4):
                if not reg.is_volunteer:
                    _answer_with_alert('Only administrators or volunteers can approve tweets')
                    return
            else:
                _answer_with_alert('Unknown twitter post policy')
                return

        # Schedule an answer to the callback query
        send_channel_message(messaging, '__telegram_internal', json.dumps({
            'command': 'answerCallbackQuery',
            'param': {
                'callback_query_id': cb['id'],
            }
        }))

        if m.group(2) == 'approve':
            tweet.approved = True
            tweet.approvedby = fromuser
            tweet.save(update_fields=['approved', 'approvedby'])
            notify_twitter_moderation(tweet, completed=True, approved=True)
            trigger_immediate_job_run('post_media_broadcasts')
        else:
            tweet.approvedby = fromuser
            notify_twitter_moderation(tweet, completed=True, approved=False)
            tweet.delete()
