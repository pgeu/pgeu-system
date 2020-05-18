import re

# Global regexps
re_token = re.compile('[0-9a-z]{64}')

messaging_implementations = {
    'postgresqleu.util.messaging.mastodon.Mastodon': ('https://mastodon.social', False),
    'postgresqleu.util.messaging.telegram.Telegram': ('https://api.telegram.org', True),
    'postgresqleu.util.messaging.twitter.Twitter': ('https://api.twitter.com', True),
}


def messaging_implementation_choices():
    return [(k, k.split('.')[-1], v[0], v[1]) for k, v in messaging_implementations.items()]


def get_messaging_class(classname):
    if classname not in messaging_implementations:
        raise Exception("Invalid messaging class")

    pieces = classname.split('.')
    modname = '.'.join(pieces[:-1])
    classname = pieces[-1]
    mod = __import__(modname, fromlist=[classname, ])
    return getattr(mod, classname)


def get_messaging(provider):
    return get_messaging_class(provider.classname)(provider.id, provider.config)


class ProviderCache(object):
    def __init__(self):
        self.providers = {}

    def get(self, provider):
        if provider.id not in self.providers:
            self.providers[provider.id] = get_messaging_class(provider.classname)(provider.id, provider.config)
        return self.providers[provider.id]
