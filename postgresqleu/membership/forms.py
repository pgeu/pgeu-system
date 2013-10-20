from django import forms
from django.forms.fields import *

from models import *

class MemberForm(forms.ModelForm):
	class Meta:
		model = Member
		exclude = ('user', 'paiduntil', 'membersince', 'activeinvoice', 'expiry_warning_sent')
