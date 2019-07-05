from django.conf.urls import include, url
from django.conf import settings
from django.contrib import admin

import sys

import postgresqleu.static.views
import postgresqleu.newsevents.views
import postgresqleu.newsevents.backendviews
import postgresqleu.views
import postgresqleu.scheduler.views
import postgresqleu.confreg.views
import postgresqleu.confreg.backendviews
import postgresqleu.confreg.backendlookups
import postgresqleu.confreg.reporting
import postgresqleu.confreg.mobileviews
import postgresqleu.confreg.feedback
import postgresqleu.confreg.pdfschedule
import postgresqleu.confreg.volsched
import postgresqleu.confreg.checkin
import postgresqleu.confwiki.views
import postgresqleu.account.views
import postgresqleu.invoices.views
import postgresqleu.invoices.backendviews
import postgresqleu.accounting.views
import postgresqleu.accounting.backendviews
import postgresqleu.paypal.views
import postgresqleu.adyen.views
import postgresqleu.trustlypayment.views
import postgresqleu.braintreepayment.views
import postgresqleu.stripepayment.views
import postgresqleu.accountinfo.views
import postgresqleu.util.docsviews
import postgresqleu.mailqueue.backendviews

from postgresqleu.newsevents.feeds import LatestNews
from postgresqleu.confreg.feeds import LatestEvents, ConferenceNewsFeed

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
admin.autodiscover()

urlpatterns = [
]

if settings.HAS_SKIN:
    from skin_urls import PRELOAD_URLS
    urlpatterns.extend(PRELOAD_URLS)

if settings.ENABLE_PG_COMMUNITY_AUTH:
    urlpatterns.extend([
        url(r'^login/?$', postgresqleu.auth.login),
        url(r'^logout/?$', postgresqleu.auth.logout),
        url(r'^accounts/login/$', postgresqleu.auth.login),
        url(r'^accounts/logout/$', postgresqleu.auth.logout),
        url(r'^auth_receive/$', postgresqleu.auth.auth_receive),
    ])
elif settings.ENABLE_OAUTH_AUTH:
    from postgresqleu.oauthlogin.urls import oauthurlpatterns
    urlpatterns.extend(oauthurlpatterns)
else:
    from django.contrib.auth import views as auth_views
    urlpatterns.extend([
        url(r'^accounts/login/$', auth_views.LoginView.as_view(template_name='djangologin/login.html')),
        url(r'^accounts/logout/$', auth_views.LogoutView.as_view()),
    ])

urlpatterns.extend([
    # Frontpage and section headers
    url(r'^$', postgresqleu.views.index),
    url(r'^events/$', postgresqleu.views.eventsindex),
    url(r'^events/past/$', postgresqleu.views.pastevents),
    url(r'^events/series/[^/]+-(\d+)/$', postgresqleu.views.eventseries),
    url(r'^events/attendee/$', postgresqleu.views.attendee_events),

    # Global admin
    url(r'^admin/$', postgresqleu.views.admin_dashboard),
    url(r'^admin/docs/(?P<page>\w+/)?$', postgresqleu.util.docsviews.docspage),

    # News
    url(r'^admin/news/news/(.*/)?$', postgresqleu.newsevents.backendviews.edit_news),
    url(r'^admin/news/authors/(.*/)?$', postgresqleu.newsevents.backendviews.edit_author),

    # Conference management
    url(r'^events/(?P<confname>[^/]+)/register/(?P<whatfor>(self)/)?$', postgresqleu.confreg.views.register),
    url(r'^events/(?P<confname>[^/]+)/register/other/(?P<regid>(\d+)/)?$', postgresqleu.confreg.views.multireg),
    url(r'^events/(?P<confname>[^/]+)/register/other/newinvoice/$', postgresqleu.confreg.views.multireg_newinvoice),
    url(r'^events/(?P<confname>[^/]+)/register/other/b(?P<bulkid>(\d+))/$', postgresqleu.confreg.views.multireg_bulkview),
    url(r'^events/(?P<confname>[^/]+)/register/other/b(?P<bulkid>(\d+))/cancel/$', postgresqleu.confreg.views.multireg_bulk_cancel),
    url(r'^events/(?P<confname>[^/]+)/register/other/z/$', postgresqleu.confreg.views.multireg_zeropay),
    url(r'^events/(?P<confname>[^/]+)/register/change/$', postgresqleu.confreg.views.changereg),
    url(r'^events/register/attach/([a-z0-9]{64})/$', postgresqleu.confreg.views.multireg_attach),
    url(r'^events/([^/]+)/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers_user),

    url(r'^events/([^/]+)/feedback/$', postgresqleu.confreg.views.feedback),
    url(r'^events/([^/]+)/feedback/(\d+)/$', postgresqleu.confreg.views.feedback_session),
    url(r'^events/([^/]+)/feedback/conference/$', postgresqleu.confreg.views.feedback_conference),
    url(r'^events/feedback/$', postgresqleu.confreg.views.feedback_available),
    url(r'^events/([^/]+)/schedule/$', postgresqleu.confreg.views.schedule),
    url(r'^events/([^/]+)/schedule/ical/$', postgresqleu.confreg.views.schedule_ical),
    url(r'^events/([^/]+)/schedule.xcs$', postgresqleu.confreg.views.schedule_xcal),
    url(r'^events/([^/]+)/schedule.xml$', postgresqleu.confreg.views.schedule_xml),
    url(r'^events/([^/]+)/schedule/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
    url(r'^events/([^/]+)/sessions/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
    url(r'^events/([^/]+)/sessions/session/(\d+)(?:-.*)?/slides/(\d+)/.*$', postgresqleu.confreg.views.session_slides),
    url(r'^events/([^/]+)/schedule/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
    url(r'^events/([^/]+)/sessions/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
    url(r'^events/(?P<urlname>[^/]+)/volunteer/$', postgresqleu.confreg.volsched.volunteerschedule),
    url(r'^events/(?P<urlname>[^/]+)/volunteer/ical/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.volsched.ical),
    url(r'^events/([^/]+)/checkin/$', postgresqleu.confreg.checkin.landing),
    url(r'^events/([^/]+)/checkin/([a-z0-9]{64})/$', postgresqleu.confreg.checkin.checkin),
    url(r'^events/([^/]+)/checkin/([a-z0-9]{64})/api/(\w+)/$', postgresqleu.confreg.checkin.api),
    url(r'^events/([^/]+)/sessions/$', postgresqleu.confreg.views.sessionlist),
    url(r'^events/speaker/(\d+)/photo/$', postgresqleu.confreg.views.speakerphoto),
    url(r'^events/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
    url(r'^events/([^/]+)/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
    url(r'^events/([^/]+)/callforpapers/$', postgresqleu.confreg.views.callforpapers),
    url(r'^events/([^/]+)/callforpapers/(\d+|new)/$', postgresqleu.confreg.views.callforpapers_edit),
    url(r'^events/([^/]+)/callforpapers/copy/$', postgresqleu.confreg.views.callforpapers_copy),
    url(r'^events/([^/]+)/callforpapers/(\d+)/delslides/(\d+)/$', postgresqleu.confreg.views.callforpapers_delslides),
    url(r'^events/([^/]+)/callforpapers/(\d+)/speakerconfirm/$', postgresqleu.confreg.views.callforpapers_confirm),
    url(r'^events/([^/]+)/callforpapers/lookups/speakers/$', postgresqleu.confreg.views.public_speaker_lookup),
    url(r'^events/([^/]+)/callforpapers/lookups/tags/$', postgresqleu.confreg.views.public_tags_lookup),
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
    url(r'^events/([^/]+)/register/ticket/$', postgresqleu.confreg.views.download_ticket),

    # Opt out of communications
    url(r'^events/optout/$', postgresqleu.confreg.views.optout),
    url(r'^events/optout/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.views.optout),

    # Backend/admin urls
    url(r'^events/admin/$', postgresqleu.confreg.views.admin_dashboard),
    url(r'^events/admin/crossmail/$', postgresqleu.confreg.views.crossmail),
    url(r'^events/admin/crossmail/options/$', postgresqleu.confreg.views.crossmailoptions),
    url(r'^events/admin/reports/time/$', postgresqleu.confreg.reporting.timereport),
    url(r'^events/admin/([^/]+)/reports/$', postgresqleu.confreg.views.reports),
    url(r'^events/admin/([^/]+)/reports/simple/$', postgresqleu.confreg.views.simple_report),
    url(r'^events/admin/([^/]+)/reports/advanced/$', postgresqleu.confreg.views.advanced_report),
    url(r'^events/admin/([^/]+)/reports/feedback/$', postgresqleu.confreg.feedback.feedback_report),
    url(r'^events/admin/([^/]+)/reports/feedback/session/$', postgresqleu.confreg.feedback.feedback_sessions),
    url(r'^events/admin/([^/]+)/reports/schedule/$', postgresqleu.confreg.pdfschedule.pdfschedule),
    url(r'^events/admin/newconference/$', postgresqleu.confreg.backendviews.new_conference),
    url(r'^events/admin/meta/series/(.*/)?$', postgresqleu.confreg.backendviews.edit_series),
    url(r'^events/admin/meta/tshirts/(.*/)?$', postgresqleu.confreg.backendviews.edit_tshirts),
    url(r'^events/admin/lookups/accounts/$', postgresqleu.util.backendlookups.GeneralAccountLookup.lookup),
    url(r'^events/admin/lookups/country/$', postgresqleu.util.backendlookups.CountryLookup.lookup),
    url(r'^events/admin/lookups/speakers/$', postgresqleu.confreg.backendlookups.SpeakerLookup.lookup),
    url(r'^events/admin/(\w+)/$', postgresqleu.confreg.views.admin_dashboard_single),
    url(r'^events/admin/(\w+)/edit/$', postgresqleu.confreg.backendviews.edit_conference),
    url(r'^events/admin/(\w+)/superedit/$', postgresqleu.confreg.backendviews.superedit_conference),
    url(r'^events/admin/(\w+)/lookups/regs/$', postgresqleu.confreg.backendlookups.RegisteredUsersLookup.lookup),
    url(r'^events/admin/(\w+)/lookups/tags/$', postgresqleu.confreg.backendlookups.SessionTagLookup.lookup),
    url(r'^events/admin/(\w+)/mail/$', postgresqleu.confreg.views.admin_attendeemail),
    url(r'^events/admin/(\w+)/mail/(\d+)/$', postgresqleu.confreg.views.admin_attendeemail_view),
    url(r'^events/admin/(\w+)/regdashboard/$', postgresqleu.confreg.views.admin_registration_dashboard),
    url(r'^events/admin/(\w+)/regdashboard/list/$', postgresqleu.confreg.views.admin_registration_list),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/$', postgresqleu.confreg.views.admin_registration_single),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/edit/$', postgresqleu.confreg.backendviews.edit_registration),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/cancel/$', postgresqleu.confreg.views.admin_registration_cancel),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/confirm/$', postgresqleu.confreg.views.admin_registration_confirm),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/clearcode/$', postgresqleu.confreg.views.admin_registration_clearcode),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/ticket/$', postgresqleu.confreg.backendviews.view_registration_ticket),
    url(r'^events/admin/(\w+)/regdashboard/list/(\d+)/resendwelcome/$', postgresqleu.confreg.views.admin_registration_resendwelcome),
    url(r'^events/admin/(\w+)/regdashboard/list/sendmail/$', postgresqleu.confreg.backendviews.registration_dashboard_send_email),
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
    url(r'^events/admin/(\w+)/waitlist/sendmail/$', postgresqleu.confreg.views.admin_waitlist_sendmail),
    url(r'^events/admin/(\w+)/wiki/$', postgresqleu.confwiki.views.admin),
    url(r'^events/admin/(\w+)/wiki/(new|\d+)/$', postgresqleu.confwiki.views.admin_edit_page),
    url(r'^events/admin/(\w+)/signups/$', postgresqleu.confwiki.views.signup_admin),
    url(r'^events/admin/(\w+)/signups/(new|\d+)/$', postgresqleu.confwiki.views.signup_admin_edit),
    url(r'^events/admin/(\w+)/signups/(\d+)/sendmail/$', postgresqleu.confwiki.views.signup_admin_sendmail),
    url(r'^events/admin/(\w+)/signups/(\d+)/edit/(new|\d+)/$', postgresqleu.confwiki.views.signup_admin_editsignup),
    url(r'^events/admin/(\w+)/transfer/$', postgresqleu.confreg.views.transfer_reg),
    url(r'^events/admin/(?P<urlname>[^/]+)/volunteer/$', postgresqleu.confreg.volsched.volunteerschedule, {'adm': True}),
    url(r'^events/admin/(?P<urlname>[^/]+)/volunteer/ical/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.volsched.ical, {'adm': True}),
    url(r'^events/admin/(\w+)/regdays/(.*/)?$', postgresqleu.confreg.backendviews.edit_regdays),
    url(r'^events/admin/(\w+)/regclasses/(.*/)?$', postgresqleu.confreg.backendviews.edit_regclasses),
    url(r'^events/admin/(\w+)/regtypes/(.*/)?$', postgresqleu.confreg.backendviews.edit_regtypes),
    url(r'^events/admin/(\w+)/addopts/(.*/)?$', postgresqleu.confreg.backendviews.edit_additionaloptions),
    url(r'^events/admin/(\w+)/tracks/(.*/)?$', postgresqleu.confreg.backendviews.edit_tracks),
    url(r'^events/admin/(\w+)/rooms/(.*/)?$', postgresqleu.confreg.backendviews.edit_rooms),
    url(r'^events/admin/(\w+)/tags/(.*/)?$', postgresqleu.confreg.backendviews.edit_tags),
    url(r'^events/admin/(\w+)/refundpatterns/(.*/)?$', postgresqleu.confreg.backendviews.edit_refundpatterns),
    url(r'^events/admin/(\w+)/sessions/sendmail/$', postgresqleu.confreg.backendviews.conference_session_send_email),
    url(r'^events/admin/(\w+)/sessions/(.*/)?$', postgresqleu.confreg.backendviews.edit_sessions),
    url(r'^events/admin/(\w+)/scheduleslots/(.*/)?$', postgresqleu.confreg.backendviews.edit_scheduleslots),
    url(r'^events/admin/(\w+)/volunteerslots/(.*/)?$', postgresqleu.confreg.backendviews.edit_volunteerslots),
    url(r'^events/admin/(\w+)/feedbackquestions/(.*/)?$', postgresqleu.confreg.backendviews.edit_feedbackquestions),
    url(r'^events/admin/(\w+)/discountcodes/(.*/)?$', postgresqleu.confreg.backendviews.edit_discountcodes),
    url(r'^events/admin/(\w+)/accesstokens/(.*/)?$', postgresqleu.confreg.backendviews.edit_accesstokens),
    url(r'^events/admin/(\w+)/news/(.*/)?$', postgresqleu.confreg.backendviews.edit_news),
    url(r'^events/admin/(\w+)/pendinginvoices/$', postgresqleu.confreg.backendviews.pendinginvoices),
    url(r'^events/admin/(\w+)/multiregs/$', postgresqleu.confreg.backendviews.multiregs),
    url(r'^events/admin/(\w+)/purgedata/$', postgresqleu.confreg.backendviews.purge_personal_data),
    url(r'^events/admin/(\w+)/integ/twitter/$', postgresqleu.confreg.backendviews.twitter_integration),
    url(r'^events/admin/([^/]+)/talkvote/$', postgresqleu.confreg.views.talkvote),
    url(r'^events/admin/([^/]+)/talkvote/changestatus/$', postgresqleu.confreg.views.talkvote_status),
    url(r'^events/admin/([^/]+)/talkvote/vote/$', postgresqleu.confreg.views.talkvote_vote),
    url(r'^events/admin/([^/]+)/talkvote/comment/$', postgresqleu.confreg.views.talkvote_comment),

    url(r'^events/admin/(\w+)/tokendata/([a-z0-9]{64})/(\w+)\.(tsv|csv|json)$', postgresqleu.confreg.backendviews.tokendata),

    url(r'^events/sponsor/', include('postgresqleu.confsponsor.urls')),

    # "Homepage" for events
    url(r'^events/([^/]+)/$', postgresqleu.confreg.views.confhome),

    # Mobile conference stuff
    url(r'^m/(\w+)/$', postgresqleu.confreg.mobileviews.index),
    url(r'^m/(\w+)/cache.manifest/$', postgresqleu.confreg.mobileviews.cachemanifest),
    url(r'^m/(\w+)/cdj/(\d+)?$', postgresqleu.confreg.mobileviews.conferencedata),
    url(r'^m/(\w+)/newsj/$', postgresqleu.confreg.mobileviews.newsproxy),

    # Legacy event URLs
    url(r'^events/(register|feedback|schedule|sessions|talkvote|speakerprofile|callforpapers|reports)/([^/]+)/(.*)?$', postgresqleu.confreg.views.legacy_redirect),


    # Accounts
    url(r'^account/$', postgresqleu.account.views.home),

    # Second generation invoice management system
    url(r'^invoiceadmin/$', postgresqleu.invoices.views.unpaid),
    url(r'^invoiceadmin/unpaid/$', postgresqleu.invoices.views.unpaid),
    url(r'^invoiceadmin/paid/$', postgresqleu.invoices.views.paid),
    url(r'^invoiceadmin/pending/$', postgresqleu.invoices.views.pending),
    url(r'^invoiceadmin/deleted/$', postgresqleu.invoices.views.deleted),
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
    url(r'^invoices/(\d+)/refundnote/(\d+)/$', postgresqleu.invoices.views.viewrefundnote),
    url(r'^invoices/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.viewinvoice_secret),
    url(r'^invoices/(\d+)/([a-z0-9]{64})/pdf/$', postgresqleu.invoices.views.viewinvoicepdf_secret),
    url(r'^invoices/(\d+)/([a-z0-9]{64})/receipt/$', postgresqleu.invoices.views.viewreceipt_secret),
    url(r'^invoices/(\d+)/([a-z0-9]{64})/refundnote/(\d+)/$', postgresqleu.invoices.views.viewrefundnote_secret),
    url(r'^invoices/dummy/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.dummy_payment),
    url(r'^invoices/$', postgresqleu.invoices.views.userhome),
    url(r'^invoices/banktransfer/$', postgresqleu.invoices.views.banktransfer),
    url(r'^invoices/adyen_bank/(\d+)/(\d+)/$', postgresqleu.adyen.views.invoicepayment),
    url(r'^invoices/adyen_bank/(\d+)/(\d+)/(\w+)/$', postgresqleu.adyen.views.invoicepayment_secret),
    url(r'^admin/invoices/vatrates/(.*/)?$', postgresqleu.invoices.backendviews.edit_vatrate),
    url(r'^admin/invoices/vatcache/(.*/)?$', postgresqleu.invoices.backendviews.edit_vatvalidationcache),
    url(r'^admin/invoices/banktransactions/$', postgresqleu.invoices.backendviews.banktransactions),
    url(r'^admin/invoices/banktransactions/(\d+)/$', postgresqleu.invoices.backendviews.banktransactions_match),
    url(r'^admin/invoices/banktransactions/(\d+)/(\d+)/$', postgresqleu.invoices.backendviews.banktransactions_match_invoice),
    url(r'^admin/invoices/banktransactions/(\d+)/multimatch/$', postgresqleu.invoices.backendviews.banktransactions_match_multiple),
    url(r'^admin/invoices/banktransactions/(\d+)/m(\d+)/$', postgresqleu.invoices.backendviews.banktransactions_match_matcher),
    url(r'^admin/invoices/paymentmethods/(.*/)?$', postgresqleu.invoices.backendviews.edit_paymentmethod),
    url(r'^invoices/trustlypay/(\d+)/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.invoicepayment_secret),
    url(r'^trustly_notification/(\d+)/$', postgresqleu.trustlypayment.views.notification),
    url(r'^trustly_success/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.success),
    url(r'^trustly_failure/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.failure),
    url(r'^invoices/braintree/(\d+)/(\d+)/$', postgresqleu.braintreepayment.views.invoicepayment),
    url(r'^invoices/braintree/(\d+)/(\d+)/(\w+)/$', postgresqleu.braintreepayment.views.invoicepayment_secret),
    url(r'^p/braintree/$', postgresqleu.braintreepayment.views.payment_post),
    url(r'^invoices/stripepay/(\d+)/(\d+)/(\w+)/$', postgresqleu.stripepayment.views.invoicepayment_secret),
    url(r'^invoices/stripepay/(\d+)/(\d+)/(\w+)/results/$', postgresqleu.stripepayment.views.invoicepayment_results),
    url(r'^invoices/stripepay/(\d+)/(\d+)/(\w+)/cancel/$', postgresqleu.stripepayment.views.invoicepayment_cancel),
    url(r'^p/stripe/(\d+)/webhook/', postgresqleu.stripepayment.views.webhook),

    # Basic accounting system
    url(r'^accounting/$', postgresqleu.accounting.views.index),
    url(r'^accounting/(\d+)/$', postgresqleu.accounting.views.year),
    url(r'^accounting/e/(\d+)/$', postgresqleu.accounting.views.entry),
    url(r'^accounting/(\d+)/new/$', postgresqleu.accounting.views.new),
    url(r'^accounting/(\d+)/close/$', postgresqleu.accounting.views.closeyear),
    url(r'^accounting/([\d-]+)/report/(\w+)/$', postgresqleu.accounting.views.report),
    url(r'^admin/accounting/accountstructure/$', postgresqleu.accounting.backendviews.accountstructure),
    url(r'^admin/accounting/accountclasses/(.*/)?$', postgresqleu.accounting.backendviews.edit_accountclass),
    url(r'^admin/accounting/accountgroups/(.*/)?$', postgresqleu.accounting.backendviews.edit_accountgroup),
    url(r'^admin/accounting/accounts/(.*/)?$', postgresqleu.accounting.backendviews.edit_account),

    # Scheduled jobs
    url(r'^admin/jobs/$', postgresqleu.scheduler.views.index),
    url(r'^admin/jobs/(\d+)/$', postgresqleu.scheduler.views.job),
    url(r'^admin/jobs/history/$', postgresqleu.scheduler.views.history),

    # Mail queue
    url(r'^admin/mailqueue/(.*/)?$', postgresqleu.mailqueue.backendviews.edit_mailqueue),

    # Handle paypal data returns
    url(r'^p/paypal_return/(\d+)/$', postgresqleu.paypal.views.paypal_return_handler),

    # Handle adyen data returns
    url(r'^p/adyen_return/(\d+)/$', postgresqleu.adyen.views.adyen_return_handler),
    url(r'^p/adyen_notify/(\d+)/$', postgresqleu.adyen.views.adyen_notify_handler),

    # Account info callbacks
    url(r'^accountinfo/search/$', postgresqleu.accountinfo.views.search),
    url(r'^accountinfo/import/$', postgresqleu.accountinfo.views.importuser),
])

if settings.ENABLE_NEWS:
    urlpatterns.extend([
        url(r'^news/archive/$', postgresqleu.newsevents.views.newsarchive),
        url(r'news/[^/]+-(\d+)/$', postgresqleu.newsevents.views.newsitem),
        # Feeds
        url(r'^feeds/(?P<what>(news|user/[^/]+))/$', LatestNews()),
        url(r'^feeds/conf/(?P<what>[^/]+)/$', ConferenceNewsFeed()),
        url(r'^feeds/conf/(?P<confname>[^/]+)/json/$', postgresqleu.confreg.views.news_json),
    ])

if settings.ENABLE_MEMBERSHIP:
    import postgresqleu.membership.views
    import postgresqleu.membership.backendviews
    urlpatterns.extend([
        # Membership management
        url(r'^membership/$', postgresqleu.membership.views.home),
        url(r'^membership/meetings/$', postgresqleu.membership.views.meetings),
        url(r'^membership/meetings/(\d+)/$', postgresqleu.membership.views.meeting),
        url(r'^membership/meetings/(\d+)/([a-z0-9]{64})/$', postgresqleu.membership.views.meeting_by_key),
        url(r'^membership/meetings/(\d+)/proxy/$', postgresqleu.membership.views.meeting_proxy),
        url(r'^membership/meetingcode/$', postgresqleu.membership.views.meetingcode),
        url(r'^membership/members/$', postgresqleu.membership.views.userlist),
        url(r'^admin/membership/config/$', postgresqleu.membership.backendviews.edit_config),
        url(r'^admin/membership/members/sendmail/$', postgresqleu.membership.backendviews.sendmail),
        url(r'^admin/membership/members/(.*/)?$', postgresqleu.membership.backendviews.edit_member),
        url(r'^admin/membership/meetings/(.*/)?$', postgresqleu.membership.backendviews.edit_meeting),
        url(r'^admin/membership/lookups/member/$', postgresqleu.membership.backendlookups.MemberLookup.lookup),
    ])

if settings.ENABLE_ELECTIONS:
    import postgresqleu.elections.views
    import postgresqleu.elections.backendviews
    urlpatterns.extend([
        # Elections
        url(r'^elections/$', postgresqleu.elections.views.home),
        url(r'^elections/(\d+)/$', postgresqleu.elections.views.election),
        url(r'^elections/(\d+)/candidate/(\d+)/$', postgresqleu.elections.views.candidate),
        url(r'^elections/(\d+)/ownvotes/$', postgresqleu.elections.views.ownvotes),
        url(r'^admin/elections/election/(.*/)?$', postgresqleu.elections.backendviews.edit_election),
    ])

# Now extend with some fallback URLs as well
urlpatterns.extend([
    # Selectable, only used on admin site for now
    url(r'^admin/selectable/', include('selectable.urls')),

    # Admin site
    url(r'^admin/django/', admin.site.urls),

    # Fallback - send everything nonspecific to the static handler
    url(r'^(.*)/$', postgresqleu.static.views.static_fallback),
])
