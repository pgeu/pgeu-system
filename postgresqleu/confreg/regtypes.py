# This file holds some special registration types

from django.core.exceptions import ValidationError

_specialregtypes = {}
def validate_speaker_registration(reg):
	# This registration is only available if a speaker is *confirmed*
	# at this conference.
	from models import ConferenceSession
	if not ConferenceSession.objects.filter(conference=reg.conference,
											speaker=reg.attendee,
											status=1, # approved
										).exists():
		raise ValidationError('This registration type is only available if you are a confirmed speaker at this conference')

_specialregtypes['spk'] = {
	'name': 'Confirmed speaker',
	'func': validate_speaker_registration,
	}

def validate_staff_registration(reg):
	if not reg.conference.staff.filter(pk=reg.attendee.pk).exists():
		raise ValidationError('This registration type is only available if you are confirmed staff at this conference')

_specialregtypes['staff'] = {
	'name': 'Confirmed staff',
	'func': validate_staff_registration,
	}


special_reg_types = [(k,v['name']) for k,v in _specialregtypes.items()]

def validate_special_reg_type(regtypename, reg):
	if not _specialregtypes.has_key(regtypename):
		raise ValidationError('Invalid registration type record. Internal error.')

	_specialregtypes[regtypename]['func'](reg)

