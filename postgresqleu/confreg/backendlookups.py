from django.db.models import Q

from postgresqleu.util.backendlookups import LookupBase
from postgresqleu.confreg.models import ConferenceRegistration, Speaker
from postgresqleu.confreg.models import ConferenceSessionTag


class RegisteredUsersLookup(LookupBase):
    @property
    def url(self):
        return '/events/admin/{0}/lookups/regs/'.format(self.conference.urlname)

    @property
    def label_from_instance(self):
        return self._label_from_instance()

    def _label_from_instance(self):
        return lambda x: '{0} {1}<{2}>'.format(
            x.fullname,
            '({}) '.format(x.attendee.username) if x.attendee else '',
            x.email,
        )

    @classmethod
    def get_values(self, query, conference):
        return [{'id': r.id, 'value': RegisteredUsersLookup._label_from_instance(self)(r)}
                for r in ConferenceRegistration.objects.filter(
                    conference=conference,
                    payconfirmedat__isnull=False, canceledat__isnull=True).filter(
                        Q(attendee__username=query) | Q(firstname__icontains=query) | Q(lastname__icontains=query) | Q(email__icontains=query)
                    )[:30]]


class SessionTagLookup(LookupBase):
    @property
    def url(self):
        if self.conference:
            return '/events/admin/{0}/lookups/tags/'.format(self.conference.urlname)
        else:
            return None

    @property
    def label_from_instance(self):
        return lambda x: x.tag

    @classmethod
    def get_values(self, query, conference):
        return [{'id': t.id, 'value': t.tag}
                for t in ConferenceSessionTag.objects.filter(conference=conference)]


class SpeakerLookup(LookupBase):
    @property
    def url(self):
        return '/events/admin/lookups/speakers/'

    @property
    def label_from_instance(self):
        def _f(x):
            if x.user:
                return "%s (%s)" % (x.fullname, x.user.username)
            else:
                return x.fullname
        return _f

    @classmethod
    def get_values(self, query):
        return [
            {'id': s.id,
             'value': "%s (%s)" % (s.fullname, s.user.username if s.user else '')
            }
            for s in Speaker.objects.filter(
                Q(fullname__icontains=query) | Q(twittername__icontains=query) | Q(user__username__icontains=query)
            )[:30]
        ]
