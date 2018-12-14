# This file holds some special registration types

from django.core.exceptions import ValidationError

_specialregtypes = {}
def validate_speaker_registration(reg):
    # This registration is only available if a speaker is *confirmed*
    # at this conference.
    from models import ConferenceSession
    if reg.attendee is None:
        raise ValidationError('Speaker registrations have to be done by the speaker directly')
    if not ConferenceSession.objects.filter(conference=reg.conference,
                                            speaker__user=reg.attendee,
                                            status=1,  # approved
                                        ).exists():
        raise ValidationError('This registration type is only available if you are a confirmed speaker at this conference')

_specialregtypes['spk'] = {
    'name': 'Confirmed speaker',
    'func': validate_speaker_registration,
    }

def validate_speaker_or_reserve_registration(reg):
    # This registration is only available if a speaker is *confirmed*
    # or *reserve listed* at this conference.
    from models import ConferenceSession
    if reg.attendee is None:
        raise ValidationError('Speaker registrations have to be done by the speaker directly')
    if not ConferenceSession.objects.filter(conference=reg.conference,
                                            speaker__user=reg.attendee,
                                            status__in=(1, 4),  # approved/reserve
                                        ).exists():
        raise ValidationError('This registration type is only available if you are a confirmed speaker at this conference')

_specialregtypes['spkr'] = {
    'name': 'Confirmed or reserve speaker',
    'func': validate_speaker_or_reserve_registration,
    }

def validate_staff_registration(reg):
    if reg.attendee is None:
        raise ValidationError('Staff registrations have to be done by the attendee directly')
    if not reg.conference.staff.filter(pk=reg.attendee.pk).exists():
        raise ValidationError('This registration type is only available if you are confirmed staff at this conference')

_specialregtypes['staff'] = {
    'name': 'Confirmed staff',
    'func': validate_staff_registration,
    }

def validate_manual_registration(reg):
    # Always validates so we can save the record, and then we just block
    # it at confirmation.
    pass

def confirm_manual_registration(reg):
    return "This registration type needs to be manually confirmed. Please await notification from the conference organizers."

_specialregtypes['man'] = {
    'name': 'Manually confirmed',
    'func': validate_manual_registration,
    'confirmfunc': confirm_manual_registration,
    }

special_reg_types = [(k, v['name']) for k, v in _specialregtypes.items()]

def validate_special_reg_type(regtypename, reg):
    if not _specialregtypes.has_key(regtypename):
        raise ValidationError('Invalid registration type record. Internal error.')

    _specialregtypes[regtypename]['func'](reg)

def confirm_special_reg_type(regtypename, reg):
    if not _specialregtypes.has_key(regtypename):
        return
    if _specialregtypes[regtypename].has_key('confirmfunc'):
        return _specialregtypes[regtypename]['confirmfunc'](reg)
    else:
        return None
