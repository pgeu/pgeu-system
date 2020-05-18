from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_save, post_delete

import requests

# Wrapper that caches oauth information, since it very rearely updates


class OAuthProviders(object):
    def __init__(self):
        self._providers = None

    @property
    def providers(self):
        if not self._providers:
            mod = apps.get_app_config('util').get_model('OAuthApplication')
            self._providers = {a.baseurl: a for a in mod.objects.all()}
        return self._providers

    def invalidate_cache(self):
        self._providers = None


providers = OAuthProviders()


def get_oauth_client(baseurl):
    return providers.providers[baseurl].client


def get_oauth_secret(baseurl):
    return providers.providers[baseurl].secret


def has_oauth_data(baseurl):
    return baseurl in providers.providers


def _mastodon_oauth_maker(baseurl):
    # Mastodon allows automatic creation of apps
    r = requests.post('{}/api/v1/apps'.format(baseurl), data={
        'client_name': settings.ORG_SHORTNAME,
        'redirect_uris': 'urn:ietf:wg:oauth:2.0:oob',
        'scopes': 'read write:statuses write:media',
    })
    r.raise_for_status()
    j = r.json()
    return (j['client_id'], j['client_secret'])


_oauth_application_choices = {
    'mastodon': ('https://mastodon.social', 0, _mastodon_oauth_maker),
    'twitter': ('https://api.twitter.com', 1, None),
}


def oauth_application_choices():
    for n, m in _oauth_application_choices.items():
        # If the provider is "locked" to a baseurl and that baseurl is already added,
        # then don't show it in the list.
        if not (m[1] and m[0] in providers.providers):
            yield (n, n, m[0], m[1])


def oauth_application_create(app, baseurl):
    if _oauth_application_choices.get(app, None):
        if _oauth_application_choices[app][2]:
            return _oauth_application_choices[app][2](baseurl)
    return (None, None)


def _invalidate_cache(**kwargs):
    providers.invalidate_cache()


def connect_oauth_signals():
    post_save.connect(_invalidate_cache, sender=apps.get_app_config('util').get_model('OAuthApplication'))
    post_delete.connect(_invalidate_cache, sender=apps.get_app_config('util').get_model('OAuthApplication'))
