from django.conf.urls import include, url
from django.conf import settings
from django.contrib import admin

import postgresqleu.static.views
import postgresqleu.newsevents.views
import postgresqleu.views
import postgresqleu.confreg.views
import postgresqleu.confreg.backendviews
import postgresqleu.confreg.backendlookups
import postgresqleu.confreg.reporting
import postgresqleu.confreg.mobileviews
import postgresqleu.confreg.feedback
import postgresqleu.confreg.pdfschedule
import postgresqleu.confreg.volsched
import postgresqleu.confreg.docsviews
import postgresqleu.confwiki.views
import postgresqleu.membership.views
import postgresqleu.account.views
import postgresqleu.elections.views
import postgresqleu.invoicemgr.views
import postgresqleu.invoices.views
import postgresqleu.accounting.views
import postgresqleu.paypal.views
import postgresqleu.adyen.views
import postgresqleu.accountinfo.views

from postgresqleu.newsevents.feeds import LatestNews
from postgresqleu.confreg.feeds import LatestEvents

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
admin.autodiscover()


urlpatterns = [
	# Frontpage and section headers
	url(r'^$', postgresqleu.views.index),
	url(r'^events/$', postgresqleu.views.eventsindex),
	url(r'^events/past/$', postgresqleu.views.pastevents),
	url(r'^(events/services)/$', postgresqleu.static.views.static_fallback),
	url(r'^events/series/[^/]+-(\d+)/$', postgresqleu.views.eventseries),
	url(r'news/[^/]+-(\d+)/$', postgresqleu.newsevents.views.newsitem),

	# Log in/log out
	url(r'^login/?$', postgresqleu.auth.login),
	url(r'^logout/?$', postgresqleu.auth.logout),
	url(r'^accounts/login/$', postgresqleu.auth.login),
	url(r'^accounts/logout/$', postgresqleu.auth.logout),
	url(r'^auth_receive/$', postgresqleu.auth.auth_receive),

	# Feeds
	url(r'^feeds/news/$', LatestNews()),

	# Conference management
	url(r'^events/(?P<confname>[^/]+)/register/(?P<whatfor>(self)/)?$', postgresqleu.confreg.views.register),
	url(r'^events/(?P<confname>[^/]+)/register/other/(?P<regid>(\d+)/)?$', postgresqleu.confreg.views.multireg),
	url(r'^events/(?P<confname>[^/]+)/register/other/newinvoice/$', postgresqleu.confreg.views.multireg_newinvoice),
	url(r'^events/(?P<confname>[^/]+)/register/other/b(?P<bulkid>(\d+))/$', postgresqleu.confreg.views.multireg_bulkview),
	url(r'^events/(?P<confname>[^/]+)/register/other/z/$', postgresqleu.confreg.views.multireg_zeropay),
	url(r'^events/(?P<confname>[^/]+)/register/change/$', postgresqleu.confreg.views.changereg),
	url(r'^events/register/attach/([a-z0-9]{64})/$', postgresqleu.confreg.views.multireg_attach),
	url(r'^events/([^/]+)/bulkpay/$', postgresqleu.confreg.views.bulkpay),
	url(r'^events/([^/]+)/bulkpay/(\d+)/$', postgresqleu.confreg.views.bulkpay_view),
	url(r'^events/([^/]+)/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers_user),

	url(r'^events/([^/]+)/feedback/$', postgresqleu.confreg.views.feedback),
	url(r'^events/([^/]+)/feedback/(\d+)/$', postgresqleu.confreg.views.feedback_session),
	url(r'^events/([^/]+)/feedback/conference/$', postgresqleu.confreg.views.feedback_conference),
	url(r'^events/feedback/$', postgresqleu.confreg.views.feedback_available),
	url(r'^events/([^/]+)/schedule/$', postgresqleu.confreg.views.schedule),
	url(r'^events/([^/]+)/schedule/ical/$', postgresqleu.confreg.views.schedule_ical),
	url(r'^events/([^/]+)/schedule/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	url(r'^events/([^/]+)/sessions/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	url(r'^events/([^/]+)/sessions/session/(\d+)(?:-.*)?/slides/(\d+)/.*$', postgresqleu.confreg.views.session_slides),
	url(r'^events/([^/]+)/schedule/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	url(r'^events/([^/]+)/sessions/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	url(r'^events/(?P<urlname>[^/]+)/volunteer/', include(postgresqleu.confreg.volsched)),
	url(r'^events/([^/]+)/sessions/$', postgresqleu.confreg.views.sessionlist),
	url(r'^events/speaker/(\d+)/photo/$', postgresqleu.confreg.views.speakerphoto),
	url(r'^events/([^/]+)/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
	url(r'^events/([^/]+)/callforpapers/$', postgresqleu.confreg.views.callforpapers),
	url(r'^events/([^/]+)/callforpapers/(\d+|new)/$', postgresqleu.confreg.views.callforpapers_edit),
	url(r'^events/([^/]+)/callforpapers/copy/$', postgresqleu.confreg.views.callforpapers_copy),
	url(r'^events/([^/]+)/callforpapers/(\d+)/delslides/(\d+)/$', postgresqleu.confreg.views.callforpapers_delslides),
	url(r'^events/([^/]+)/callforpapers/(\d+)/speakerconfirm/$', postgresqleu.confreg.views.callforpapers_confirm),
	url(r'^events/([^/]+)/register/confirm/$', postgresqleu.confreg.views.confirmreg),
	url(r'^events/([^/]+)/register/waitlist_signup/$', postgresqleu.confreg.views.waitlist_signup),
	url(r'^events/([^/]+)/register/waitlist_cancel/$', postgresqleu.confreg.views.waitlist_cancel),
	url(r'^events/([^/]+)/register/canceled/$', postgresqleu.confreg.views.cancelreg),
	url(r'^events/([^/]+)/register/invoice/(\d+)/$', postgresqleu.confreg.views.invoice),
	url(r'^events/([^/]+)/register/invoice/(\d+)/cancel/$', postgresqleu.confreg.views.invoice_cancel),
	url(r'^events/([^/]+)/register/mail/(\d+)/$', postgresqleu.confreg.views.attendee_mail),
	url(r'^events/([^/]+)/register/addopt/$', postgresqleu.confreg.views.reg_add_options),
	url(r'^events/([^/]+)/register/wiki/(.*)/edit/$', postgresqleu.confwiki.views.wikipage_edit),
	url(r'^events/([^/]+)/register/wiki/(.*)/history/$', postgresqleu.confwiki.views.wikipage_history),
	url(r'^events/([^/]+)/register/wiki/(.*)/sub/$', postgresqleu.confwiki.views.wikipage_subscribe),
	url(r'^events/([^/]+)/register/wiki/(.*)/$', postgresqleu.confwiki.views.wikipage),
	url(r'^events/([^/]+)/register/signup/(\d+)/$', postgresqleu.confwiki.views.signup),

	# Opt out of communications
	url(r'^events/optout/$', postgresqleu.confreg.views.optout),
	url(r'^events/optout/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.views.optout),

	# Backend/admin urls
	url(r'^events/admin/$', postgresqleu.confreg.views.admin_dashboard),
	url(r'^events/admin/crossmail/$', postgresqleu.confreg.views.crossmail),
	url(r'^events/admin/crossmail/options/$', postgresqleu.confreg.views.crossmailoptions),
	url(r'^events/admin/reports/time/$', postgresqleu.confreg.reporting.timereport),
	url(r'^events/admin/(?P<urlname>[^/]+/)?docs/(?P<page>\w+/)?$', postgresqleu.confreg.docsviews.docspage),
	url(r'^events/admin/([^/]+)/reports/$', postgresqleu.confreg.views.reports),
	url(r'^events/admin/([^/]+)/reports/simple/$', postgresqleu.confreg.views.simple_report),
	url(r'^events/admin/([^/]+)/reports/advanced/$', postgresqleu.confreg.views.advanced_report),
	url(r'^events/admin/([^/]+)/reports/feedback/$', postgresqleu.confreg.feedback.feedback_report),
	url(r'^events/admin/([^/]+)/reports/feedback/session/$', postgresqleu.confreg.feedback.feedback_sessions),
	url(r'^events/admin/([^/]+)/reports/schedule/$', postgresqleu.confreg.pdfschedule.pdfschedule),
	url(r'^events/admin/newconference/$', postgresqleu.confreg.backendviews.new_conference),
	url(r'^events/admin/meta/series/(.*/)?$', postgresqleu.confreg.backendviews.edit_series),
	url(r'^events/admin/lookups/accounts/$', postgresqleu.confreg.backendlookups.GeneralAccountLookup.lookup),
	url(r'^events/admin/lookups/speakers/$', postgresqleu.confreg.backendlookups.SpeakerLookup.lookup),
	url(r'^events/admin/(\w+)/$', postgresqleu.confreg.views.admin_dashboard_single),
	url(r'^events/admin/(\w+)/edit/$', postgresqleu.confreg.backendviews.edit_conference),
	url(r'^events/admin/(\w+)/superedit/$', postgresqleu.confreg.backendviews.superedit_conference),
	url(r'^events/admin/(\w+)/lookups/regs/$', postgresqleu.confreg.backendlookups.RegisteredUsersLookup.lookup),
	url(r'^events/admin/(\w+)/mail/$', postgresqleu.confreg.views.admin_attendeemail),
	url(r'^events/admin/(\w+)/mail/(\d+)/$', postgresqleu.confreg.views.admin_attendeemail_view),
	url(r'^events/admin/(\w+)/regdashboard/$', postgresqleu.confreg.views.admin_registration_dashboard),
	url(r'^events/admin/(\w+)/regdashboard/list/$', postgresqleu.confreg.views.admin_registration_list),
	url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/$', postgresqleu.confreg.views.admin_registration_single),
	url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/edit/$', postgresqleu.confreg.backendviews.edit_registration),
	url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/cancel/$', postgresqleu.confreg.views.admin_registration_cancel),
	url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/clearcode/$', postgresqleu.confreg.views.admin_registration_clearcode),
	url(r'^events/admin/(\w+)/prepaid/$', postgresqleu.confreg.views.createvouchers),
	url(r'^events/admin/(\w+)/prepaid/list/$', postgresqleu.confreg.views.listvouchers),
	url(r'^events/admin/(\w+)/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers),
	url(r'^events/admin/(\w+)/prepaid/(\d+)/del/(\d+)/$', postgresqleu.confreg.views.delvouchers),
	url(r'^events/admin/(\w+)/prepaid/(\d+)/send_email/$', postgresqleu.confreg.views.emailvouchers),
	url(r'^events/admin/([^/]+)/schedule/create/$', postgresqleu.confreg.views.createschedule),
	url(r'^events/admin/([^/]+)/schedule/create/publish/$', postgresqleu.confreg.views.publishschedule),
	url(r'^events/admin/([^/]+)/schedule/jsonschedule/$', postgresqleu.confreg.views.schedulejson),
	url(r'^events/admin/([^/]+)/sessionnotifyqueue/$', postgresqleu.confreg.views.session_notify_queue),
	url(r'^events/admin/(\w+)/waitlist/$', postgresqleu.confreg.views.admin_waitlist),
	url(r'^events/admin/(\w+)/waitlist/cancel/(\d+)/$', postgresqleu.confreg.views.admin_waitlist_cancel),
	url(r'^events/admin/(\w+)/wiki/$', postgresqleu.confwiki.views.admin),
	url(r'^events/admin/(\w+)/wiki/(new|\d+)/$', postgresqleu.confwiki.views.admin_edit_page),
	url(r'^events/admin/(\w+)/signups/$', postgresqleu.confwiki.views.signup_admin),
	url(r'^events/admin/(\w+)/signups/(new|\d+)/$', postgresqleu.confwiki.views.signup_admin_edit),
	url(r'^events/admin/(\w+)/signups/(\d+)/sendmail/$', postgresqleu.confwiki.views.signup_admin_sendmail),
	url(r'^events/admin/(\w+)/signups/(\d+)/edit/(new|\d+)/$', postgresqleu.confwiki.views.signup_admin_editsignup),
	url(r'^events/admin/(\w+)/transfer/$', postgresqleu.confreg.views.transfer_reg),
	url(r'^events/admin/(?P<urlname>[^/]+)/volunteer/', include(postgresqleu.confreg.volsched), {'adm': True}),
	url(r'^events/admin/(\w+)/regdays/(.*/)?$', postgresqleu.confreg.backendviews.edit_regdays),
	url(r'^events/admin/(\w+)/regclasses/(.*/)?$', postgresqleu.confreg.backendviews.edit_regclasses),
	url(r'^events/admin/(\w+)/regtypes/(.*/)?$', postgresqleu.confreg.backendviews.edit_regtypes),
	url(r'^events/admin/(\w+)/addopts/(.*/)?$', postgresqleu.confreg.backendviews.edit_additionaloptions),
	url(r'^events/admin/(\w+)/tracks/(.*/)?$', postgresqleu.confreg.backendviews.edit_tracks),
	url(r'^events/admin/(\w+)/rooms/(.*/)?$', postgresqleu.confreg.backendviews.edit_rooms),
	url(r'^events/admin/(\w+)/sessions/(.*/)?$', postgresqleu.confreg.backendviews.edit_sessions),
	url(r'^events/admin/(\w+)/scheduleslots/(.*/)?$', postgresqleu.confreg.backendviews.edit_scheduleslots),
	url(r'^events/admin/(\w+)/volunteerslots/(.*/)?$', postgresqleu.confreg.backendviews.edit_volunteerslots),
	url(r'^events/admin/(\w+)/feedbackquestions/(.*/)?$', postgresqleu.confreg.backendviews.edit_feedbackquestions),
	url(r'^events/admin/(\w+)/discountcodes/(.*/)?$', postgresqleu.confreg.backendviews.edit_discountcodes),
	url(r'^events/admin/(\w+)/accesstokens/(.*/)?$', postgresqleu.confreg.backendviews.edit_accesstokens),
	url(r'^events/admin/(\w+)/pendinginvoices/$', postgresqleu.confreg.backendviews.pendinginvoices),
	url(r'^events/admin/(\w+)/purgedata/$', postgresqleu.confreg.backendviews.purge_personal_data),
	url(r'^events/admin/([^/]+)/talkvote/$', postgresqleu.confreg.views.talkvote),
	url(r'^events/admin/([^/]+)/talkvote/changestatus/$', postgresqleu.confreg.views.talkvote_status),
	url(r'^events/admin/([^/]+)/talkvote/vote/$', postgresqleu.confreg.views.talkvote_vote),
	url(r'^events/admin/([^/]+)/talkvote/comment/$', postgresqleu.confreg.views.talkvote_comment),

	url(r'^events/admin/(\w+)/tokendata/([a-z0-9]{64})/(\w+)\.(tsv|csv)$', postgresqleu.confreg.backendviews.tokendata),

	url(r'^events/sponsor/', include('postgresqleu.confsponsor.urls')),

	# "Homepage" for events
	url(r'^events/([^/]+)/$', postgresqleu.confreg.views.confhome),

	# Mobile conference stuff
	url(r'^m/(\w+)/$', postgresqleu.confreg.mobileviews.index),
	url(r'^m/(\w+)/cache.manifest/$', postgresqleu.confreg.mobileviews.cachemanifest),
	url(r'^m/(\w+)/cdj/(\d+)?$', postgresqleu.confreg.mobileviews.conferencedata),
	url(r'^m/(\w+)/newsj/$', postgresqleu.confreg.mobileviews.newsproxy),


	# Conference admin
	url(r'^admin/confreg/_email/$', postgresqleu.confreg.views.admin_email),
	url(r'^admin/confreg/_email_session_speaker/([,\d]+)/$', postgresqleu.confreg.views.admin_email_session),

	# Legacy event URLs
	url(r'^events/(register|bulkpay|feedback|schedule|sessions|talkvote|speakerprofile|callforpapers|reports)/([^/]+)/(.*)?$', postgresqleu.confreg.views.legacy_redirect),


	# Membership management
	url(r'^membership/$', postgresqleu.membership.views.home),
	url(r'^membership/meetings/$', postgresqleu.membership.views.meetings),
	url(r'^membership/meetings/(\d+)/$', postgresqleu.membership.views.meeting),
	url(r'^membership/meetings/(\d+)/([a-z0-9]{64})/$', postgresqleu.membership.views.meeting_by_key),
	url(r'^membership/meetings/(\d+)/proxy/$', postgresqleu.membership.views.meeting_proxy),
	url(r'^membership/meetingcode/$', postgresqleu.membership.views.meetingcode),
	url(r'^community/members/$', postgresqleu.membership.views.userlist),
	url(r'^admin/membership/_email/$', postgresqleu.membership.views.admin_email),

	# Accounts
	url(r'^account/$', postgresqleu.account.views.home),

	# Elections
	url(r'^elections/$', postgresqleu.elections.views.home),
	url(r'^elections/(\d+)/$', postgresqleu.elections.views.election),
	url(r'^elections/(\d+)/candidate/(\d+)/$', postgresqleu.elections.views.candidate),
	url(r'^elections/(\d+)/ownvotes/$', postgresqleu.elections.views.ownvotes),

	# Invoice manager (admins only!)
	url(r'invoicemgr/$', postgresqleu.invoicemgr.views.home),
	url(r'invoicemgr/(\d+)/$', postgresqleu.invoicemgr.views.invoice),
	url(r'invoicemgr/(\d+)/pdf/$', postgresqleu.invoicemgr.views.invoicepdf),

	# Second generation invoice management system
	url(r'^invoiceadmin/$', postgresqleu.invoices.views.unpaid),
	url(r'^invoiceadmin/unpaid/$', postgresqleu.invoices.views.unpaid),
	url(r'^invoiceadmin/all/$', postgresqleu.invoices.views.all),
	url(r'^invoiceadmin/pending/$', postgresqleu.invoices.views.pending),
	url(r'^invoiceadmin/deleted/$', postgresqleu.invoices.views.deleted),
	url(r'^invoiceadmin/refunded/$', postgresqleu.invoices.views.refunded),
	url(r'^invoiceadmin/search/$', postgresqleu.invoices.views.search),
	url(r'^invoiceadmin/(\d+)/$', postgresqleu.invoices.views.oneinvoice),
	url(r'^invoiceadmin/(new)/$', postgresqleu.invoices.views.oneinvoice),
	url(r'^invoiceadmin/(\d+)/flag/$', postgresqleu.invoices.views.flaginvoice),
	url(r'^invoiceadmin/(\d+)/cancel/$', postgresqleu.invoices.views.cancelinvoice),
	url(r'^invoiceadmin/(\d+)/refund/$', postgresqleu.invoices.views.refundinvoice),
	url(r'^invoiceadmin/(\d+)/preview/$', postgresqleu.invoices.views.previewinvoice),
	url(r'^invoiceadmin/(\d+)/send_email/$', postgresqleu.invoices.views.emailinvoice),
	url(r'^invoiceadmin/(\d+)/extend_cancel/$', postgresqleu.invoices.views.extend_cancel),
	url(r'^invoices/(\d+)/$', postgresqleu.invoices.views.viewinvoice),
	url(r'^invoices/(\d+)/pdf/$', postgresqleu.invoices.views.viewinvoicepdf),
	url(r'^invoices/(\d+)/receipt/$', postgresqleu.invoices.views.viewreceipt),
	url(r'^invoices/(\d+)/refundnote/$', postgresqleu.invoices.views.viewrefundnote),
	url(r'^invoices/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.viewinvoice_secret),
	url(r'^invoices/(\d+)/([a-z0-9]{64})/pdf/$', postgresqleu.invoices.views.viewinvoicepdf_secret),
	url(r'^invoices/(\d+)/([a-z0-9]{64})/receipt/$', postgresqleu.invoices.views.viewreceipt_secret),
	url(r'^invoices/(\d+)/([a-z0-9]{64})/refundnote/$', postgresqleu.invoices.views.viewrefundnote_secret),
	url(r'^invoices/dummy/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.dummy_payment),
	url(r'^invoices/$', postgresqleu.invoices.views.userhome),
	url(r'^invoices/banktransfer/$', postgresqleu.invoices.views.banktransfer),
	url(r'^invoices/adyen_bank/(\d+)/$', postgresqleu.adyen.views.invoicepayment),
	url(r'^invoices/adyen_bank/(\d+)/(\w+)/$', postgresqleu.adyen.views.invoicepayment_secret),

	# Basic accounting system
	url(r'^accounting/$', postgresqleu.accounting.views.index),
	url(r'^accounting/(\d+)/$', postgresqleu.accounting.views.year),
	url(r'^accounting/e/(\d+)/$', postgresqleu.accounting.views.entry),
	url(r'^accounting/(\d+)/new/$', postgresqleu.accounting.views.new),
	url(r'^accounting/(\d+)/close/$', postgresqleu.accounting.views.closeyear),
	url(r'^accounting/([\d-]+)/report/(\w+)/$', postgresqleu.accounting.views.report),

	# Handle paypal data returns
	url(r'^p/paypal_return/$', postgresqleu.paypal.views.paypal_return_handler),

	# Handle adyen data returns
	url(r'^p/adyen_return/$', postgresqleu.adyen.views.adyen_return_handler),
	url(r'^p/adyen_notify/$', postgresqleu.adyen.views.adyen_notify_handler),

	# Account info callbacks
	url(r'^accountinfo/search/$', postgresqleu.accountinfo.views.search),
	url(r'^accountinfo/import/$', postgresqleu.accountinfo.views.importuser),
]

if settings.ENABLE_TRUSTLY:
	import postgresqleu.trustlypayment.views

	urlpatterns.extend([
		url(r'^invoices/trustlypay/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.invoicepayment_secret),
		url(r'^trustly_notification/$', postgresqleu.trustlypayment.views.notification),
		url(r'^trustly_success/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.success),
		url(r'^trustly_failure/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.failure),
	])

if settings.ENABLE_BRAINTREE:
	import postgresqleu.braintreepayment.views

	urlpatterns.extend([
		url(r'^invoices/braintree/(\d+)/$', postgresqleu.braintreepayment.views.invoicepayment),
		url(r'^invoices/braintree/(\d+)/(\w+)/$', postgresqleu.braintreepayment.views.invoicepayment_secret),
		url(r'^p/braintree/$', postgresqleu.braintreepayment.views.payment_post),
	])



# Now extend with some fallback URLs as well
urlpatterns.extend([
	# Selectable, only used on admin site for now
	url(r'^admin/selectable/', include('selectable.urls')),

	# Admin site
    url(r'^admin/', include(admin.site.urls)),

	# Fallback - send everything nonspecific to the static handler
	url(r'^(.*)/$', postgresqleu.static.views.static_fallback),
])
