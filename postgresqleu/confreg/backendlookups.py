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
        return lambda x: '{0} <{1}>'.format(x.fullname, x.email)

    @classmethod
    def get_values(self, query, conference):
        return [{'id': r.id, 'value': r.fullname}
                for r in ConferenceRegistration.objects.filter(
                    conference=conference,
                    payconfirmedat__isnull=False, canceledat__isnull=True).filter(
                        Q(firstname__icontains=query) | Q(lastname__icontains=query) | Q(email__icontains=query)
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
        return lambda x: "%s (%s)" % (x.fullname, x.user.username)

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
