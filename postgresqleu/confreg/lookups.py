from selectable.base import ModelLookup
from selectable.registry import registry
from selectable.decorators import staff_member_required

from postgresqleu.confreg.models import ConferenceRegistration


@staff_member_required
class RegistrationLookup(ModelLookup):
    model = ConferenceRegistration
    search_fields = (
        'attendee__username__icontains',
        'firstname__icontains',
        'lastname__icontains',
        'email__icontains',
    )

    def get_query(self, request, term):
        q = super(RegistrationLookup, self).get_query(request, term)
        if 'conference' in request.GET:
            return q.filter(conference_id=request.GET['conference'], payconfirmedat__isnull=False)
        else:
            # Don't return anything if parameter not present
            return None

    def get_item_value(self, item):
        # Display for currently selected item
        return u"%s (%s %s)" % (item.attendee and item.attendee.username or '(no account)', item.firstname, item.lastname)

    def get_item_label(self, item):
        # Display for choice listings
        return u"%s (%s %s)" % (item.attendee and item.attendee.username or '(no account)', item.firstname, item.lastname)


registry.register(RegistrationLookup)
