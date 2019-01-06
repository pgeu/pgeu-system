#
# Script to register twitter oauth privileges for the main news posting
#
# NOTE! Conferences are registered directly from the conference management
# interface!
#
#

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests_oauthlib


class Command(BaseCommand):
    help = 'Register with twitter oauth'

    def handle(self, *args, **options):
        if not settings.TWITTER_CLIENT:
            raise CommandError("TWITTER_CLIENT must be set in settings_local.py")
        if not settings.TWITTER_CLIENTSECRET:
            raise CommandError("TWITTER_CLIENTSECRET must be set in settings_local.py")
        if settings.TWITTER_NEWS_TOKEN:
            raise CommandError("TWITTER_NEWS_TOKEN is already set in settings_local.py")
        if settings.TWITTER_NEWS_TOKENSECRET:
            raise CommandError("TWITTER_NEWS_TOKENSECRET is already set in settings_local.py")

        # OK, now we're good to go :)
        oauth = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT, settings.TWITTER_CLIENTSECRET)
        fetch_response = oauth.fetch_request_token('https://api.twitter.com/oauth/request_token')

        authorization_url = oauth.authorization_url('https://api.twitter.com/oauth/authorize')
        print 'Please go here and authorize: %s' % authorization_url

        pin = input('Paste the PIN here: ')

        oauth = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT,
                                                settings.TWITTER_CLIENTSECRET,
                                                resource_owner_key=fetch_response.get('oauth_token'),
                                                resource_owner_secret=fetch_response.get('oauth_token_secret'),
                                                verifier=pin)
        oauth_tokens = oauth.fetch_access_token('https://api.twitter.com/oauth/access_token')

        print("Authorized. Please configure:")
        print("TWITTER_NEWS_TOKEN='%s'" % oauth_tokens.get('oauth_token'))
        print("TWITTER_NEWS_TOKENSECRET='%s'" % oauth_tokens.get('oauth_token_secret'))
        print("In your local_settings.py!")
