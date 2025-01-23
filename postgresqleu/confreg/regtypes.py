# This file holds some special registration types

from django.core.exceptions import ValidationError
from django.db.models import Q

_specialregtypes = {}


def validate_speaker_registration(reg, reqstatuses=(1, )):
    # This registration is only available if a speaker is *confirmed*
    # at this conference.
    from .models import ConferenceSession
    if reg.attendee is None:
        raise ValidationError('Speaker registrations have to be done by the speaker directly')

    trackQ = Q(track__isnull=True) | Q(track__speakerreg=True)
    if not ConferenceSession.objects.filter(conference=reg.conference,
                                            speaker__user=reg.attendee,
                                            status__in=reqstatuses,  # approved
                                        ).filter(trackQ).exists():
        # If the speaker has approved talks on the "wrong" track, then give a nicer error message
        slist = list(ConferenceSession.objects.filter(conference=reg.conference,
                                                      speaker__user=reg.attendee,
                                                      status__in=reqstatuses,
        ))
        if slist and slist[0].track:
            raise ValidationError('This registration type is not available to you as sessions on track "{0}" are not eligible for free registration'.format(slist[0].track.trackname))

        raise ValidationError('This registration type is only available if you are a confirmed speaker at this conference')


_specialregtypes['spk'] = {
    'name': 'Confirmed speaker',
    'func': validate_speaker_registration,
    }


def validate_speaker_or_reserve_registration(reg):
    # This registration is only available if a speaker is *confirmed*
    # or *reserve listed* at this conference.
    validate_speaker_registration(reg, reqstatuses=(1, 4))


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


def validate_cfpmember_registration(reg):
    if reg.attendee is None:
        raise ValidationError('CFP team member registrations have to be done by the attendee directly')
    if not reg.conference.talkvoters.filter(pk=reg.attendee.pk).exists():
        raise ValidationError('This registration type is only available if you are confirmed CFP team member at this conference')


_specialregtypes['cfp'] = {
    'name': 'CFP team member',
    'func': validate_cfpmember_registration,
    }


def validate_manual_registration(reg):
    # Always validates so we can save the record, and then we just block
    # it at confirmation. This doesn't work well with multiregs, so just
    # block them for multireg for now.
    if reg.ismultireg:
        raise ValidationError('This registration type can only be used for individually made registrations')


def confirm_manual_registration(reg):
    return "This registration type needs to be manually confirmed. Please await notification from the conference organizers."


def confirm_manual_registration_setup(cleaned_data):
    if cleaned_data['cost'] > 0:
        raise ValidationError('This special type cannot be used for paid registrations.')


_specialregtypes['man'] = {
    'name': 'Manually confirmed',
    'func': validate_manual_registration,
    'confirmfunc': confirm_manual_registration,
    'confirmsetupfunc': confirm_manual_registration_setup,
    }


def validate_voucher_registration_form(reg, cleaned_data):
    from .models import PrepaidVoucher

    if cleaned_data.get('vouchercode', '') == '' or not PrepaidVoucher.objects.filter(conference=reg.conference, vouchervalue=cleaned_data['vouchercode']).exists():
        yield ('regtype', 'This registration type is only available if you have a specific voucher for it.')


_specialregtypes['vch'] = {
    'name': 'Requires specific voucher',
    'formfunc': validate_voucher_registration_form,
}


special_reg_types = [(k, v['name']) for k, v in sorted(list(_specialregtypes.items()))]


def validate_special_reg_type(regtypename, reg):
    if regtypename not in _specialregtypes:
        raise ValidationError('Invalid registration type record. Internal error.')

    if 'func' in _specialregtypes[regtypename]:
        _specialregtypes[regtypename]['func'](reg)


def validate_special_reg_type_form(regtypename, reg, cleaned_data):
    if regtypename not in _specialregtypes:
        raise ValidationError('Invalid registration type record. Internal error.')

    if 'formfunc' in _specialregtypes[regtypename]:
        return _specialregtypes[regtypename]['formfunc'](reg, cleaned_data) or ()
    return ()


def confirm_special_reg_type(regtypename, reg):
    if regtypename not in _specialregtypes:
        return
    if 'confirmfunc' in _specialregtypes[regtypename]:
        return _specialregtypes[regtypename]['confirmfunc'](reg)
    else:
        return None


def validate_special_reg_type_setup(regtypename, cleaned_data):
    if regtypename not in _specialregtypes:
        raise ValidationError('Invalid registration type record. Internal error.')

    if 'confirmsetupfunc' in _specialregtypes[regtypename]:
        _specialregtypes[regtypename]['confirmsetupfunc'](cleaned_data)
