digisign_providers = {
    'postgresqleu.digisign.implementations.signwell.Signwell': (),
}


def digisign_provider_choices():
    return [(k, k.split('.')[-1]) for k, v in digisign_providers.items()]


digisign_handlers = {}


def register_digisign_handler(key, handler):
    digisign_handlers[key] = handler


class DigisignHandlerBase:
    def __init__(self, doc):
        self.doc = doc

    def completed(self):
        pass

    def expired(self):
        pass

    def declined(self):
        pass

    def canceled(self):
        pass
