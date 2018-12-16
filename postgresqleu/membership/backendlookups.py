from django.db.models import Q

from postgresqleu.util.backendlookups import LookupBase
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.membership.models import Member


class MemberLookup(LookupBase):
    url = '/admin/membership/lookups/member/'

    @property
    def label_from_instance(self):
        return lambda x: u'{0} ({1})'.format(x.fullname, x.user.username)

    @classmethod
    def get_values(self, query):
        return [
            {'id': m.pk, 'value': m.fullname}
            for m in Member.objects.filter(paiduntil__isnull=False).filter(
                Q(fullname__icontains=query) | Q(user__username__icontains=query))[:30]]

    @classmethod
    def validate_global_access(self, request):
        authenticate_backend_group(request, 'Membership administrators')
