from django import forms
from django.forms import RadioSelect
from django.forms import ValidationError
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import escape

from django.db.models.fields.files import ImageFieldFile

from models import Conference, ConferenceRegistration, RegistrationType, Speaker
from models import ConferenceAdditionalOption, Track
from models import ConferenceSession, ConferenceSessionFeedback
from models import PrepaidVoucher

from regtypes import validate_special_reg_type

from postgresqleu.countries.models import Country

class ConferenceRegistrationForm(forms.ModelForm):
	additionaloptions = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
		required=False,
		queryset=ConferenceAdditionalOption.objects.all())

	def __init__(self, user, *args, **kwargs):
		super(ConferenceRegistrationForm, self).__init__(*args, **kwargs)
		self.user = user
		self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference).order_by('sortkey')
		if not self.instance.conference.asktshirt:
			del self.fields['shirtsize']
		self.fields['additionaloptions'].queryset =	ConferenceAdditionalOption.objects.filter(
			conference=self.instance.conference)
		self.fields['country'].queryset = Country.objects.order_by('printable_name')

	def clean_regtype(self):
		newval = self.cleaned_data.get('regtype')
		if self.instance and newval == self.instance.regtype:
			# Registration type not changed, so it's ok to save
			# (we don't want to prohibit other edits for somebody who has
			#  an already-made registration with an expired registration type)
			return newval

		if newval and not newval.active:
			raise forms.ValidationError('Registration type "%s" is currently not available.' % newval)

		if self.instance and self.instance.payconfirmedat:
			raise forms.ValidationError('You cannot change type of registration once your payment has been confirmed!')

		if newval and newval.specialtype:
			validate_special_reg_type(newval.specialtype, self.instance)

		return newval

	def clean_vouchercode(self):
		newval = self.cleaned_data.get('vouchercode')
		if newval=='': return newval

		try:
			v = PrepaidVoucher.objects.get(vouchervalue=newval, conference=self.instance.conference)
			if v.usedate:
				raise forms.ValidationError('This voucher has already been used')
		except PrepaidVoucher.DoesNotExist:
			raise forms.ValidationError('This voucher was not found')

		return newval


	def compare_options(self, a, b):
		# First check if the sizes are the same
		if len(a) != len(b):
			return False

		# Then do a very expensive one-by-one check
		for x in a:
			found = False
			for y in b:
				if x.pk == y.pk:
					found = True
					break
			if not found:
				# Entry in a not found in b, give up
				return False

		# All entires in a were in b, and the sizes were the same..
		return True

	def clean_additionaloptions(self):
		newval = self.cleaned_data.get('additionaloptions')

		if self.instance and self.instance.pk:
			oldval = list(self.instance.additionaloptions.all())
		else:
			oldval = ()

		if self.instance and self.compare_options(newval, oldval):
			# Additional options not changed, so keep allowing them
			return newval

		# Check that the new selection is available by doing a count
		# We only look at the things that have been *added*
		for option in set(newval).difference(oldval):
			if option.maxcount == -1:
				raise forms.ValidationError("The option \"%s\" is currently not available." % option.name)
			if option.maxcount > 0:
				# This option has a limit on the number of people
				# Count how many others have it. The difference we took on
				# the sets above means we only check this when *this*
				# registration doesn't have the option, and thus the count
				# will always increase by one if we save this.
				current_count = option.conferenceregistration_set.count()
				if current_count + 1 > option.maxcount:
					raise forms.ValidationError("The option \"%s\" is no longer available due to too many signups." % option.name)

		# Check if the registration has been confirmed
		if self.instance and self.instance.payconfirmedat:
			raise forms.ValidationError('You cannot change your additional options once your payment has been confirmed! If you need to make changes, please contact the conference organizers via email')

		# Yeah, it's ok
		return newval

	def clean(self):
		# At the form level, validate anything that has references between
		# different fields, since they are not saved until we get here.
		# Note that if one of those fields have failed validation on their
		# own, they will not be present in cleaned_data.
		cleaned_data = super(ConferenceRegistrationForm, self).clean()

		if cleaned_data.has_key('vouchercode') and cleaned_data['vouchercode']:
			# We know it's there, and that it exists - but is it for the
			# correct type of registration?
			v = PrepaidVoucher.objects.get(vouchervalue=cleaned_data['vouchercode'],
										   conference=self.instance.conference)
			if v.batch.regtype != cleaned_data['regtype']:
				self._errors['vouchercode'] = self.error_class('The specified voucher is only usable for registrations of type "%s"' % v.batch.regtype)

		return cleaned_data

	class Meta:
		model = ConferenceRegistration
		exclude = ('conference','attendee','payconfirmedat','payconfirmedby','created',)

	@property
	def fieldsets(self):
		# Return a set of fields used for our rendering
		conf = self.instance.conference

		yield {'id': 'personal_information',
			   'legend': 'Personal information',
			   'introhtml': mark_safe(u'<p>You are currently making a registration for community account<br/><i>{0} ({1} {2} &lt;{3}&gt;).</p>'.format(escape(self.user.username), escape(self.user.first_name), escape(self.user.last_name), escape(self.user.email))),
			   'fields': [self[x] for x in ('regtype', 'firstname', 'lastname', 'company', 'address', 'country', 'email', 'phone', 'twittername', 'nick')],
			   }

		if conf.asktshirt or conf.askfood or conf.askshareemail:
			fields = []
			if conf.asktshirt: fields.append(self['shirtsize'])
			if conf.askfood: fields.append(self['dietary'])
			if conf.askshareemail: fields.append(self['shareemail'])
			yield {'id': 'conference_info',
				   'legend': 'Conference information',
				   'fields': fields}

		if conf.conferenceadditionaloption_set.all().exists():
			yield {'id': 'additional_options',
				   'legend': 'Additional options',
				   'intro': conf.additionalintro,
				   'fields': [self['additionaloptions'],],
				   }

		yield { 'id': 'voucher_codes',
				'legend': 'Voucher codes',
				'intro': 'If you have a voucher code, enter it in this field. If you do not have one, just leave the field empty.',
				'fields': [self['vouchercode'],],
				}

rating_choices = (
    (1, '1 (Worst)'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5 (Best)'),
    (0, 'N/A'),
)

class ConferenceSessionFeedbackForm(forms.ModelForm):
	topic_importance = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Importance of the topic')
	content_quality = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Quality of the content')
	speaker_knowledge = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Speakers knowledge of the subject')
	speaker_quality = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Speakers presentation skills')

	class Meta:
		model = ConferenceSessionFeedback
		exclude = ('conference','attendee','session')


class ConferenceFeedbackForm(forms.Form):
	# Very special dynamic form. It's ugly, but hey, it works
	def __init__(self, *args, **kwargs):
		questions = kwargs.pop('questions')
		responses = kwargs.pop('responses')

		super(ConferenceFeedbackForm, self).__init__(*args, **kwargs)

		# Now add our custom fields
		for q in questions:
			if q.isfreetext:
				if q.textchoices:
					self.fields['question_%s' % q.id] = forms.ChoiceField(widget=RadioSelect,
																		  choices=[(x,x) for x in q.textchoices.split(";")],
																		  label=q.question,
																		  initial=self.get_answer_text(responses, q.id))
				else:
					self.fields['question_%s' % q.id] = forms.CharField(widget=forms.widgets.Textarea,
																		label=q.question,
																		required=False,
																		initial=self.get_answer_text(responses, q.id))
			else:
				self.fields['question_%s' % q.id] = forms.ChoiceField(widget=RadioSelect,
																	  choices=rating_choices,
																	  label=q.question,
																	  initial=self.get_answer_num(responses, q.id))

			# Overload fieldset on help_text. Really really really ugly, but a way to get the fieldset
			# out into the form without having to subclass things.
			self.fields['question_%s' % q.id].help_text = q.newfieldset

	def get_answer_text(self, responses, id):
		for r in responses:
			if r.question_id == id:
				return r.textanswer
		return ""

	def get_answer_num(self, responses, id):
		for r in responses:
			if r.question_id == id:
				return r.rateanswer
		return -1

class SpeakerProfileForm(forms.ModelForm):
	class Meta:
		model = Speaker
		exclude = ('user', )

	def clean_photofile(self):
		if not self.cleaned_data['photofile']:
			return self.cleaned_data['photofile'] # If it's None...
		if isinstance(self.cleaned_data['photofile'], ImageFieldFile):
			return self.cleaned_data['photofile'] # If it's unchanged...

		img = None
		try:
			from PIL import ImageFile
			p = ImageFile.Parser()
			p.feed(self.cleaned_data['photofile'].read())
			p.close()
			img = p.image
		except Exception, e:
			raise ValidationError("Could not parse image: %s" % e)
		if img.format != 'JPEG':
			raise ValidationError("Only JPEG format images are accepted, not '%s'" % img.format)
		if img.size[0] > 128 or img.size[1] > 128:
			raise ValidationError("Maximum image size is 128x128")
		return self.cleaned_data['photofile']

	def clean_twittername(self):
		if not self.cleaned_data['twittername']:
			return self.cleaned_data['twittername']
		if not self.cleaned_data['twittername'][0] == '@':
			return "@%s" % self.cleaned_data['twittername']
		return self.cleaned_data['twittername']

	def clean_fullname(self):
		if not self.cleaned_data['fullname'].strip():
			raise ValidationError("Your full name must be given. This will be used both in the speaker profile and in communications with the conference organizers.")
		return self.cleaned_data['fullname']

class CallForPapersForm(forms.ModelForm):
	class Meta:
		model = ConferenceSession
		exclude = ('conference', 'speaker', 'starttime', 'endtime',
				   'room', 'cross_schedule', 'can_feedback', 'status',
				   'initialsubmit', 'tentativescheduleslot', 'tentativeroom')

	def __init__(self, *args, **kwargs):
		super(CallForPapersForm, self).__init__(*args, **kwargs)
		if not self.instance.conference.skill_levels:
			del self.fields['skill_level']
		if not self.instance.conference.track_set.count() > 0:
			del self.fields['track']
		else:
			self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference).order_by('trackname')

	def clean_abstract(self):
		abstract = self.cleaned_data.get('abstract')
		if len(abstract) < 30:
			raise ValidationError("Submitted abstract is too short (must be at least 30 characters)")
		return abstract

	def clean_track(self):
		if not self.cleaned_data.get('track'):
			raise ValidationError("Please choose the track that is the closest match to your talk")
		return self.cleaned_data.get('track')


class PrepaidCreateForm(forms.Form):
	conference = forms.ModelChoiceField(queryset=Conference.objects.filter(active=True))
	regtype = forms.ModelChoiceField(queryset=RegistrationType.objects.all())
	count = forms.IntegerField(min_value=1, max_value=100)
	buyer = forms.ModelChoiceField(queryset=User.objects.all().order_by('username'), help_text="Pick the user who bought the batch. If he/she is not registered, pick your own userid")
	confirm = forms.BooleanField(help_text="Confirm that the chosen registration type and count are correct (there is no undo past this point, the vouchers will be created!")

	def __init__(self, *args, **kwargs):
		super(PrepaidCreateForm, self).__init__(*args, **kwargs)
		if self.data and self.data.has_key('conference'):
			self.fields['regtype'].queryset=RegistrationType.objects.filter(conference=self.data.get('conference'))
			if not (self.data.has_key('regtype')
					and self.data.has_key('count')
					and self.data.get('regtype')
					and self.data.get('count')):
				del self.fields['confirm']
		else:
			# No conference selected, so remove other fields
			del self.fields['regtype']
			del self.fields['count']
			del self.fields['buyer']
			del self.fields['confirm']

class EmailSendForm(forms.Form):
	ids = forms.CharField(label="List of id's", widget=forms.widgets.HiddenInput())
	returnurl = forms.CharField(label="Return url", widget=forms.widgets.HiddenInput())
	sender = forms.EmailField(label="Sending email")
	subject = forms.CharField(label="Subject", min_length=10)
	text = forms.CharField(label="Email text", min_length=50, widget=forms.Textarea)
	confirm = forms.BooleanField(help_text="Confirm that you really want to send this email! Double and triple check the text and sender!")

	def __init__(self, *args, **kwargs):
		super(EmailSendForm, self).__init__(*args, **kwargs)
		self.fields['ids'].widget.attrs['readonly'] = True
		readytogo = False
		if self.data and self.data.has_key('ids') and self.data.has_key('sender') and self.data.has_key('subject') and self.data.has_key('text'):
			if len(self.data['ids']) > 1 and len(self.data['sender']) > 5 and len(self.data['subject']) > 10 and len(self.data['text']) > 50:
				readytogo = True
		if not readytogo:
			del self.fields['confirm']

class EmailSessionForm(forms.Form):
	sender = forms.EmailField(label="Sending email")
	subject = forms.CharField(label="Subject", min_length=10)
	returnurl = forms.CharField(label="Return url", widget=forms.widgets.HiddenInput(), required=False)
	text = forms.CharField(label="Email text", min_length=50, widget=forms.Textarea)
	confirm = forms.BooleanField(help_text="Confirm that you really want to send this email! Double and triple check the text and sender!")

	def __init__(self, *args, **kwargs):
		super(EmailSessionForm, self).__init__(*args, **kwargs)
		readytogo = False
		if self.data and self.data.has_key('sender') and self.data.has_key('subject') and self.data.has_key('text'):
			if len(self.data['sender']) > 5 and len(self.data['subject']) > 10 and len(self.data['text']) > 50:
				readytogo = True
		if not readytogo:
			del self.fields['confirm']


class BulkRegistrationForm(forms.Form):
	recipient_name = forms.CharField(required=True, max_length=100,label='Invoice recipient name')
	recipient_address = forms.CharField(required=True, max_length=100, label='Invoice recipient address', widget=forms.Textarea)
	email_list = forms.CharField(required=True, label='Emails to pay for', widget=forms.Textarea)

	def clean_email_list(self):
		email_list = self.cleaned_data.get('email_list')
		emails = [e for e in email_list.splitlines(False) if e]
		if len(emails) < 2:
			raise ValidationError('Bulk payments can only be done for 2 or more emails')
		return email_list
