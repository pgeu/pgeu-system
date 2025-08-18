from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from postgresqleu.confreg.util import get_authenticated_conference
from postgresqleu.confreg.models import Conference
from postgresqleu.countries.models import Country

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
                                          startdate__gt=timezone.now() - datetime.timedelta(days=90)).exists()):
            raise PermissionDenied("Access denied.")

    @classmethod
    def lookup(self, request, urlname=None):
        if urlname is None:
            self.validate_global_access(request)
            vals = self.get_values(request.GET['query'])
        else:
            conference = get_authenticated_conference(request, urlname)
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
        return lambda x: '{0} {1} ({2})'.format(x.first_name, x.last_name, x.username)

    @classmethod
    def get_values(self, query):
        return [
            {
                'id': u.id,
                'value': '{0} {1} ({2}) <{3}>'.format(u.first_name, u.last_name, u.username, u.email),
                'email': u.email.lower(),
            }
            for u in User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
            )[:30]
        ]


class CountryLookup(LookupBase):
    @property
    def url(self):
        return '/events/admin/lookups/country/'

    @property
    def label_from_instance(self):
        return lambda x: x.printable_name

    @classmethod
    def get_values(self, query):
        return [
            {
                'id': c.iso,
                'value': c.printable_name,
            }
            for c in Country.objects.filter(
                Q(printable_name__icontains=query) | Q(iso__icontains=query)
            )[:30]
        ]
