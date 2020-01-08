from django.conf import settings

import requests_oauthlib

_cached_twitter_users = {}


class Twitter(object):
    def __init__(self, conference=None):
        if conference:
            token = conference.twitter_token
            secret = conference.twitter_secret
        else:
            token = settings.TWITTER_NEWS_TOKEN
            secret = settings.TWITTER_NEWS_TOKENSECRET

        self.tw = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT,
                                                  settings.TWITTER_CLIENTSECRET,
                                                  token,
                                                  secret)

    def get_own_screen_name(self):
        r = self.tw.get('https://api.twitter.com/1.1/account/verify_credentials.json?include_entities=false&skip_status=true&include_email=false')
        if r.status_code != 200:
            raise Exception("http status {}".format(r.status_code))
        return r.json()['screen_name']

    def post_tweet(self, tweet, image=None, replytotweetid=None):
        d = {
            'status': tweet,
        }
        if replytotweetid:
            d['in_reply_to_status_id'] = replytotweetid
            d['auto_populate_reply_metadata'] = True

        if image:
            # Images are separately uploaded as a first step
            r = self.tw.post('https://upload.twitter.com/1.1/media/upload.json', files={
                'media': bytearray(image),
            })
            if r.status_code != 200:
                return (False, 'Media upload: {}'.format(r.text))
            d['media_ids'] = r.json()['media_id']

        r = self.tw.post('https://api.twitter.com/1.1/statuses/update.json', data=d)
        if r.status_code != 200:
            return (None, r.text)
        return (r.json()['id'], None)

    def retweet(self, tweetid):
        r = self.tw.post('https://api.twitter.com/1.1/statuses/retweet/{0}.json'.format(tweetid))
        if r.status_code != 200:
            return (None, r.text)
        return (True, None)

    def send_message(self, tousername, msg):
        # Nor the username
        tousername = tousername.lower().replace('@', '')

        # DM API calls require us to look up the userid, so do that with a
        # tiny cache first.
        if tousername not in _cached_twitter_users:
            try:
                r = self.tw.get('https://api.twitter.com/1.1/users/show.json',
                                params={'screen_name': tousername})
                _cached_twitter_users[tousername] = r.json()['id']
            except Exception as e:
                return (False, None, "Failed to look up user %s: %s" % (tousername, e))

        try:
            r = self.tw.post('https://api.twitter.com/1.1/direct_messages/events/new.json', json={
                'event': {
                    'type': 'message_create',
                    'message_create': {
                        'target': {
                            'recipient_id': _cached_twitter_users[tousername],
                        },
                        'message_data': {
                            'text': msg,
                        }
                    }
                }
            })
            if r.status_code != 200:
                try:
                    # Normally these errors come back as json
                    ej = r.json()['errors'][0]
                    return (False, ej['code'], ej['message'])
                except Exception as e:
                    return (False, None, r.text)
        except Exception as e:
            return (False, None, e)
        return (True, None, None)

    def get_timeline(self, tlname, since=None):
        if since:
            sincestr = "&since={}".format(since)
        else:
            sincestr = ""
        r = self.tw.get('https://api.twitter.com/1.1/statuses/{}_timeline.json?tweet_mode=extended{}'.format(tlname, sincestr))
        if r.status_code != 200:
            return None
        return r.json()


class TwitterSetup(object):
    @classmethod
    def get_authorization_data(self):
        oauth = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT, settings.TWITTER_CLIENTSECRET)
        fetch_response = oauth.fetch_request_token('https://api.twitter.com/oauth/request_token')
        auth_url = oauth.authorization_url('https://api.twitter.com/oauth/authorize')

        return (auth_url,
                fetch_response.get('oauth_token'),
                fetch_response.get('oauth_token_secret'),
        )

    @classmethod
    def authorize(self, ownerkey, ownersecret, pincode):
        oauth = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT,
                                                settings.TWITTER_CLIENTSECRET,
                                                resource_owner_key=ownerkey,
                                                resource_owner_secret=ownersecret,
                                                verifier=pincode)
        tokens = oauth.fetch_access_token('https://api.twitter.com/oauth/access_token')

        return tokens
