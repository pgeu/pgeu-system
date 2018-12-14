import imageupload
import requireclaiming
import entryvouchers
import providetext
import attendeelist

def _make_benefit(n, c):
    all_benefits[n] = {'name': c.description, 'class': c}

all_benefits = {}
# We hardcode this list to ensure the integer sequence is the same as it's stored
# in a db. Yes, it's kinda ugly...
_make_benefit(1, imageupload.ImageUpload)
_make_benefit(2, requireclaiming.RequireClaiming)
_make_benefit(3, entryvouchers.EntryVouchers)
_make_benefit(4, providetext.ProvideText)
_make_benefit(5, attendeelist.AttendeeList)
