from django import forms
from django.forms import RadioSelect
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import escape

from django.db.models.fields.files import ImageFieldFile

from models import Conference, ConferenceRegistration, RegistrationType, Speaker
from models import ConferenceAdditionalOption, Track, RegistrationClass
from models import ConferenceSession, ConferenceSessionFeedback
from models import PrepaidVoucher, DiscountCode, AttendeeMail

from regtypes import validate_special_reg_type
from postgresqleu.util.validators import TwitterValidator

from postgresqleu.countries.models import Country

from datetime import datetime, date

class ConferenceRegistrationForm(forms.ModelForm):
	additionaloptions = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
		required=False,
		queryset=ConferenceAdditionalOption.objects.all(),
		label='Additional options')

	def __init__(self, user, *args, **kwargs):
		super(ConferenceRegistrationForm, self).__init__(*args, **kwargs)
		self.user = user
		self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference).order_by('sortkey')
		if not self.instance.conference.asktshirt:
			del self.fields['shirtsize']
		self.fields['additionaloptions'].queryset =	ConferenceAdditionalOption.objects.filter(
			conference=self.instance.conference, public=True)
		self.fields['country'].queryset = Country.objects.order_by('printable_name')
		self.fields['twittername'].validators.append(TwitterValidator)

	def clean_regtype(self):
		newval = self.cleaned_data.get('regtype')
		if self.instance and newval == self.instance.regtype:
			# Registration type not changed, so it's ok to save
			# (we don't want to prohibit other edits for somebody who has
			#  an already-made registration with an expired registration type)
			return newval

		if newval and not newval.active:
			raise forms.ValidationError('Registration type "%s" is currently not available.' % newval)

		if newval and newval.activeuntil and newval.activeuntil < datetime.today().date():
			raise forms.ValidationError('Registration type "%s" was only available until %s.' % (newval, newval.activeuntil))

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
			# It could be that it's a discount code
			try:
				c = DiscountCode.objects.get(code=newval, conference=self.instance.conference)
				if c.is_invoiced:
					raise forms.ValidationError('This discount code is not valid anymore.')
				if c.validuntil and c.validuntil < date.today():
					raise forms.ValidationError('This discount code has expired.')
				if c.maxuses > 0:
					if c.registrations.count() >= c.maxuses:
						raise forms.ValidationError('All allowed instances of this discount code have been used.')

				required_regtypes = c.requiresregtype.all()
				if required_regtypes:
					# If the list is empty, any goes. But if there's something
					# in the list, we have to enforce it.
					if not self.cleaned_data.get('regtype') in required_regtypes:
						raise forms.ValidationError("This discount code is only valid for registration type(s): {0}".format(", ".join([r.regtype for r in required_regtypes])))

				selected = self.cleaned_data.get('additionaloptions') or ()
				for o in c.requiresoption.all():
					if not o in selected:
						raise forms.ValidationError("This discount code requires the option '%s' to be picked." % o)

			except DiscountCode.DoesNotExist:
				raise forms.ValidationError('This voucher or discount code was not found')

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

		for option in newval:
			# Check if something mutually exclusive is included
			for x in option.mutually_exclusive.all():
				if x in newval:
					raise forms.ValidationError('The option "%s" cannot be ordered at the same time as "%s".' % (option.name, x.name))

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
			errs = []
			try:
				v = PrepaidVoucher.objects.get(vouchervalue=cleaned_data['vouchercode'],
											   conference=self.instance.conference)
				if not cleaned_data.has_key('regtype'):
					errs.append('Invalid registration type specified')
					raise ValidationError('An invalid registration type has been selected')
				if v.batch.regtype != cleaned_data['regtype']:
					errs.append('The specified voucher is only usable for registrations of type "%s"' % v.batch.regtype)
			except PrepaidVoucher.DoesNotExist:
				# This must have been a discount code :)
				try:
					DiscountCode.objects.get(code=cleaned_data['vouchercode'],
											 conference=self.instance.conference)
					# Validity of the code has already been validated, and it's not tied
					# to a specific one, so as long as it exists, we're good to go.
				except DiscountCode.DoesNotExist:
					errs.append('Specified voucher or discount code does not exist')

			if errs:
				self._errors['vouchercode'] = ErrorList(errs)

		if cleaned_data.has_key('regtype') and cleaned_data['regtype']:
			if cleaned_data['regtype'].requires_option.exists():
				regtype = cleaned_data['regtype']
				found = False
				if cleaned_data.has_key('additionaloptions') and cleaned_data['additionaloptions']:
					for x in regtype.requires_option.all():
						if x in cleaned_data['additionaloptions']:
							found = True
							break
				if not found:
					self._errors['regtype'] = 'Registration type "%s" requires at least one of the following additional options to be picked: %s' % (regtype, ", ".join([x.name for x in regtype.requires_option.all()]))

		if cleaned_data.has_key('additionaloptions') and cleaned_data['additionaloptions'] and cleaned_data.has_key('regtype'):
			regtype = cleaned_data['regtype']
			errs = []
			for ao in cleaned_data['additionaloptions']:
				if ao.requires_regtype.exists():
					if not regtype in ao.requires_regtype.all():
						errs.append('Additional option "%s" requires one of the following registration types: %s.' % (ao.name, ", ".join(x.regtype for x in ao.requires_regtype.all())))
			if len(errs):
				self._errors['additionaloptions'] = self.error_class(errs)

		return cleaned_data

	class Meta:
		model = ConferenceRegistration
		exclude = ('conference','attendee','payconfirmedat','payconfirmedby','created', 'regtoken')

	@property
	def fieldsets(self):
		# Return a set of fields used for our rendering
		conf = self.instance.conference

		yield {'id': 'personal_information',
			   'legend': 'Personal information',
			   'introhtml': mark_safe(u'<p>You are currently making a registration for community account<br/><i>{0} ({1} {2} &lt;{3}&gt;).</i></p>'.format(escape(self.user.username), escape(self.user.first_name), escape(self.user.last_name), escape(self.user.email))),
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

		if conf.conferenceadditionaloption_set.filter(public=True).exists():
			yield {'id': 'additional_options',
				   'legend': 'Additional options',
				   'intro': conf.additionalintro,
				   'fields': [self['additionaloptions'],],
				   }

		yield { 'id': 'voucher_codes',
				'legend': 'Voucher codes',
				'intro': 'If you have a voucher or discount code, enter it in this field. If you do not have one, just leave the field empty.',
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


class CallForPapersSpeakerForm(forms.Form):
	email = forms.EmailField()

	def clean_email(self):
		if not Speaker.objects.filter(user__email=self.cleaned_data['email']).exists():
			raise ValidationError("No speaker profile for user with email %s exists." % self.cleaned_data['email'])
		return self.cleaned_data['email']

class CallForPapersSubmissionForm(forms.Form):
	title = forms.CharField(required=True, max_length=200, min_length=10)

class CallForPapersForm(forms.ModelForm):
	class Meta:
		model = ConferenceSession
		exclude = ('conference', 'speaker', 'starttime', 'endtime',
				   'room', 'cross_schedule', 'can_feedback', 'status',
				   'initialsubmit', 'tentativescheduleslot', 'tentativeroom',
				   'lastnotifiedstatus', 'lastnotifiedtime', )

	def __init__(self, *args, **kwargs):
		super(CallForPapersForm, self).__init__(*args, **kwargs)
		if not self.instance.conference.skill_levels:
			del self.fields['skill_level']
		if not self.instance.conference.track_set.filter(incfp=True).count() > 0:
			del self.fields['track']
		else:
			self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference, incfp=True).order_by('trackname')

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
	buyername = forms.CharField(max_length=100,help_text="Display name of the user who bought the batch. Internal use and copied to invoice")
	invoice = forms.BooleanField(help_text="Automatically create invoice template for these vouchers. Note that the vouchers are created immediately, not at payment time!", required=False)
	confirm = forms.BooleanField(help_text="Confirm that the chosen registration type and count are correct (there is no undo past this point, the vouchers will be created!")

	def __init__(self, *args, **kwargs):
		super(PrepaidCreateForm, self).__init__(*args, **kwargs)
		if self.data and self.data.has_key('conference'):
			self.fields['regtype'].queryset=RegistrationType.objects.filter(conference=self.data.get('conference'))
			if not (self.data.has_key('regtype')
					and self.data.has_key('count')
					and self.data.get('regtype')
					and self.data.get('buyername')
					and self.data.get('count')):
				del self.fields['confirm']
		else:
			# No conference selected, so remove other fields
			del self.fields['regtype']
			del self.fields['count']
			del self.fields['buyer']
			del self.fields['buyername']
			del self.fields['confirm']
			del self.fields['invoice']

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

class AttendeeMailForm(forms.ModelForm):
	confirm = forms.BooleanField(label="Confirm", required=False)
	class Meta:
		model = AttendeeMail
		exclude = ('conference', )

	def __init__(self, conference, *args, **kwargs):
		self.conference = conference
		super(AttendeeMailForm, self).__init__(*args, **kwargs)

		self.fields['regclasses'].widget = forms.CheckboxSelectMultiple()
		self.fields['regclasses'].queryset = RegistrationClass.objects.filter(conference=self.conference)

		if not (self.data.get('regclasses') and self.data.get('subject') and self.data.get('message')):
			del self.fields['confirm']

	def clean_confirm(self):
		if not self.cleaned_data['confirm']:
			raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")


class WaitlistOfferForm(forms.Form):
	hours = forms.IntegerField(min_value=1, max_value=240, label='Offer valid for (hours)', initial=48)
	confirm = forms.BooleanField(help_text='Confirm')

	def __init__(self, *args, **kwargs):
		super(WaitlistOfferForm, self).__init__(*args, **kwargs)
		if self.data and self.data.has_key('hours'):
			self.reg_list = self._get_id_list_from_data()
			self.fields['confirm'].help_text = "Confirm that you want to send an offer to {0} attendees on the waitlist".format(len(self.reg_list))
		else:
			del self.fields['confirm']

	def _get_id_list_from_data(self):
		if not self.data: return []
		l = []
		for k,v in self.data.items():
			if v == '1' and k.startswith('reg_'):
				l.append(int(k[4:]))
		return l

	def clean(self):
		if len(self.reg_list)==0:
			raise ValidationError("At least one registration must be selected to make an offer")
		return self.cleaned_data


class CrossConferenceMailForm(forms.Form):
	senderaddr = forms.EmailField(min_length=5, required=True)
	sendername = forms.CharField(min_length=5, required=True)
	attendees_of = forms.ModelMultipleChoiceField(queryset=Conference.objects.all(), label="Send to attendees of")
	attendees_not_of = forms.ModelMultipleChoiceField(queryset=Conference.objects.all(), label="Who are not attendees of", required=False)
	subject = forms.CharField(min_length=10, max_length=80, required=True)
	text = forms.CharField(min_length=30, required=True, widget=forms.Textarea)

	confirm = forms.BooleanField(label="Confirm", required=False)

	def __init__(self, *args, **kwargs):
		super(CrossConferenceMailForm, self).__init__(*args, **kwargs)

		if not (self.data.get('senderaddr') and self.data.get('sendername') and self.data.get('attendees_of') and self.data.get('subject') and self.data.get('text')):
			del self.fields['confirm']

	def clean_confirm(self):
		if not self.cleaned_data['confirm']:
			raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")
