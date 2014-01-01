from django import forms

from models import Member

class MemberForm(forms.ModelForm):
	class Meta:
		model = Member
		exclude = ('user', 'paiduntil', 'membersince', 'activeinvoice', 'expiry_warning_sent')
