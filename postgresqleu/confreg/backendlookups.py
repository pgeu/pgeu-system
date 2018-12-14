from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.db.models import Q

import backendviews
from models import Conference, ConferenceRegistration, Speaker

import datetime
import json

class LookupBase(object):
    def __init__(self, conference=None):
        self.conference = conference

    @classmethod
    def validate_global_access(self, request):
        # User must be admin of some conference in the past 3 months (just to add some overlap)
        # or at some point in the future.
        if not (request.user.is_superuser or
                Conference.objects.filter(Q(administrators=request.user) | Q(series__administrators=request.user),
                                          startdate__gt=datetime.datetime.now()-datetime.timedelta(days=90)).exists()):
            raise PermissionDenied("Access denied.")

    @classmethod
    def lookup(self, request, urlname=None):
        if urlname is None:
            self.validate_global_access(request)
            vals = self.get_values(request.GET['query'])
        else:
            conference = backendviews.get_authenticated_conference(request, urlname)
            vals = self.get_values(request.GET['query'], conference)

        return HttpResponse(json.dumps({
            'values': vals,
        }), content_type='application/json')

class GeneralAccountLookup(LookupBase):
    @property
    def url(self):
        return '/events/admin/lookups/accounts/'

    @property
    def label_from_instance(self):
        return lambda x: u'{0} {1} ({2})'.format(x.first_name, x.last_name, x.username)


    @classmethod
    def get_values(self, query):
        return [{'id': u.id, 'value': u'{0} {1} ({2})'.format(u.first_name, u.last_name, u.username)}
                for u in User.objects.filter(
                        Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
                )[:30]]


class RegisteredUsersLookup(LookupBase):
    @property
    def url(self):
        return '/events/admin/{0}/lookups/regs/'.format(self.conference.urlname)

    @property
    def label_from_instance(self):
        return lambda x: u'{0} <{1}>'.format(x.fullname, x.email)

    @classmethod
    def get_values(self, query, conference):
        return [{'id': r.id, 'value': r.fullname}
                for r in ConferenceRegistration.objects.filter(
                        conference=conference,
                        payconfirmedat__isnull=False).filter(
                            Q(firstname__icontains=query) | Q(lastname__icontains=query) | Q(email__icontains=query)
                        )[:30]]


class SpeakerLookup(LookupBase):
    @property
    def url(self):
        return '/events/admin/lookups/speakers/'

    @property
    def label_from_instance(self):
        return lambda x: u"%s (%s)" % (x.fullname, x.user.username)

    @classmethod
    def get_values(self, query):
        return [{'id': s.id, 'value': u"%s (%s)" % (s.fullname, s.user.username if s.user else '')}
                for s in Speaker.objects.filter(
                        Q(fullname__icontains=query) | Q(twittername__icontains=query) | Q(user__username__icontains=query)
                )[:30]]
