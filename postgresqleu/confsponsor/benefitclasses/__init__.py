# NOTE! id fields are stored in database!
all_benefits = {
    0: {"class": None, "description": "Automatically claimed"},
    1: {"class": "imageupload.ImageUpload", "description": 'Require uploaded image'},
    2: {"class": "requireclaiming.RequireClaiming", "description": "Requires explicit claiming"},
    3: {"class": "entryvouchers.EntryVouchers", "description": "Claim entry vouchers"},
    4: {"class": "providetext.ProvideText", "description": "Provide text string"},
    5: {"class": "attendeelist.AttendeeList", "description": "List of attendee email addresses"},
    6: {"class": "badgescanning.BadgeScanning", "description": "Scanning of attendee badges"},
    7: {"class": "sponsorsession.SponsorSession", "description": "Submit session"},
    8: {"class": "fileupload.FileUpload", "description": 'Upload file'},
}


def get_benefit_id(classname):
    return next((k for k, v in all_benefits.items() if v['class'] == classname))
