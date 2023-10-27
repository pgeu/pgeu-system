from django.utils import timezone


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
        self.doc.completed = timezone.now()
        self.doc.save(update_fields=['completed', ])

    def expired(self):
        pass

    def declined(self):
        pass

    def canceled(self):
        pass

    def signed(self, signedby):
        if not self.doc.firstsigned:
            # This is the first signature (for most docs, it means the counterpart)
            self.doc.firstsigned = timezone.now()
            self.doc.save(update_fields=['firstsigned', ])
