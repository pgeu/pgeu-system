# NOTE! id fields are stored in database!
all_benefits = {
    1: {"class": "imageupload.ImageUpload", "description": 'Require uploaded image'},
    2: {"class": "requireclaiming.RequireClaiming", "description": "Requires explicit claiming"},
    3: {"class": "entryvouchers.EntryVouchers", "description": "Claim entry vouchers"},
    4: {"class": "providetext.ProvideText", "description": "Provide text string"},
    5: {"class": "attendeelist.AttendeeList", "description": "List of attendee email addresses"},
}
