from django.urls import include
from django.urls import path, re_path
from django.conf import settings
from django.contrib import admin

import postgresqleu.static.views
import postgresqleu.newsevents.views
import postgresqleu.newsevents.backendviews
import postgresqleu.views
import postgresqleu.scheduler.views
import postgresqleu.confreg.views
import postgresqleu.confreg.backendviews
import postgresqleu.confreg.backendlookups
import postgresqleu.confreg.reporting
import postgresqleu.confreg.feedback
import postgresqleu.confreg.pdfschedule
import postgresqleu.confreg.volsched
import postgresqleu.confreg.checkin
import postgresqleu.confreg.twitter
import postgresqleu.confreg.api
import postgresqleu.confreg.upload
import postgresqleu.confsponsor.scanning
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
import postgresqleu.transferwise.views
import postgresqleu.plaid.backendviews
import postgresqleu.plaid.views
import postgresqleu.gocardless.backendviews
import postgresqleu.accountinfo.views
import postgresqleu.util.docsviews
import postgresqleu.mailqueue.backendviews
import postgresqleu.digisign.backendviews
import postgresqleu.digisign.views
import postgresqleu.util.monitor
import postgresqleu.util.views
import postgresqleu.util.backendviews
import postgresqleu.util.pgauth

from postgresqleu.newsevents.feeds import LatestNews
from postgresqleu.confreg.feeds import ConferenceNewsFeed

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
        re_path(r'^login/?$', postgresqleu.auth.login),
        re_path(r'^logout/?$', postgresqleu.auth.logout),
        re_path(r'^accounts/login/$', postgresqleu.auth.login),
        re_path(r'^accounts/logout/$', postgresqleu.auth.logout),
        re_path(r'^auth_receive/$', postgresqleu.auth.auth_receive),
        re_path(r'^auth_api/$', postgresqleu.util.pgauth.auth_api),
    ])
elif settings.ENABLE_OAUTH_AUTH:
    from postgresqleu.oauthlogin.urls import oauthurlpatterns
    urlpatterns.extend(oauthurlpatterns)
else:
    from django.contrib.auth import views as auth_views
    urlpatterns.extend([
        re_path(r'^accounts/login/$', auth_views.LoginView.as_view(template_name='djangologin/login.html')),
        re_path(r'^accounts/logout/$', auth_views.LogoutView.as_view()),
    ])

urlpatterns.extend([
    # Frontpage and section headers
    re_path(r'^$', postgresqleu.views.index),
    re_path(r'^events/$', postgresqleu.views.eventsindex),
    re_path(r'^events/past/$', postgresqleu.views.pastevents),
    re_path(r'^events/series/[^/]+-(\d+)/$', postgresqleu.views.eventseries),
    re_path(r'^events/attendee/$', postgresqleu.views.attendee_events),

    # Global admin
    re_path(r'^admin/$', postgresqleu.views.admin_dashboard),
    re_path(r'^admin/docs/(?P<page>\w+/)?$', postgresqleu.util.docsviews.docspage),
    re_path(r'^admin/mdpreview/$', postgresqleu.util.views.markdown_preview),

    # News
    re_path(r'^admin/news/news/(.*/)?$', postgresqleu.newsevents.backendviews.edit_news),
    re_path(r'^admin/news/authors/(.*/)?$', postgresqleu.newsevents.backendviews.edit_author),
    re_path(r'^admin/news/postqueue/(.*/?)$', postgresqleu.newsevents.backendviews.edit_postqueue),
    re_path(r'^admin/news/messagingproviders/(.*/?)$', postgresqleu.newsevents.backendviews.edit_messagingproviders),

    # Conference management
    re_path(r'^events/(?P<confname>[^/]+)/register/(?P<whatfor>(self)/)?$', postgresqleu.confreg.views.register),
    re_path(r'^events/(?P<confname>[^/]+)/register/other/(?P<regid>(\d+)/)?$', postgresqleu.confreg.views.multireg),
    re_path(r'^events/(?P<confname>[^/]+)/register/other/newinvoice/$', postgresqleu.confreg.views.multireg_newinvoice),
    re_path(r'^events/(?P<confname>[^/]+)/register/other/b(?P<bulkid>(\d+))/$', postgresqleu.confreg.views.multireg_bulkview),
    re_path(r'^events/(?P<confname>[^/]+)/register/other/b(?P<bulkid>(\d+))/cancel/$', postgresqleu.confreg.views.multireg_bulk_cancel),
    re_path(r'^events/(?P<confname>[^/]+)/register/other/z/$', postgresqleu.confreg.views.multireg_zeropay),
    re_path(r'^events/(?P<confname>[^/]+)/register/change/$', postgresqleu.confreg.views.changereg),
    re_path(r'^events/(?P<confname>[^/]+)/register/msgconfig/$', postgresqleu.confreg.views.reg_config_messaging),
    re_path(r'^events/(?P<confname>[^/]+)/register/startover/$', postgresqleu.confreg.views.reg_start_over),
    re_path(r'^events/(?P<confname>[^/]+)/register/cancelreg/$', postgresqleu.confreg.views.reg_cancel_request),
    re_path(r'^events/register/attach/([a-z0-9]{64})/?$', postgresqleu.confreg.views.multireg_attach),
    re_path(r'^events/register/policy/([a-z0-9]{64})/?$', postgresqleu.confreg.views.regconfirmpolicy_token),
    re_path(r'^events/([^/]+)/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers_user),

    re_path(r'^events/([^/]+)/feedback/$', postgresqleu.confreg.views.feedback),
    re_path(r'^events/([^/]+)/feedback/(\d+)/$', postgresqleu.confreg.views.feedback_session),
    re_path(r'^events/([^/]+)/feedback/conference/$', postgresqleu.confreg.views.feedback_conference),
    re_path(r'^events/([^/]+)/schedule/$', postgresqleu.confreg.views.schedule),
    re_path(r'^events/([^/]+)/schedule/fav/$', postgresqleu.confreg.views.schedule_favorite),
    re_path(r'^events/([^/]+)/schedule/ical/$', postgresqleu.confreg.views.schedule_ical),
    re_path(r'^events/([^/]+)/schedule.xcs$', postgresqleu.confreg.views.schedule_xcal),
    re_path(r'^events/([^/]+)/schedule.xml$', postgresqleu.confreg.views.schedule_xml),
    re_path(r'^events/(?P<confname>[^/]+)/(?P<section>schedule|sessions)/session/(?P<sessionid>\d+)(?P<slug>-[^/]*)?/$', postgresqleu.confreg.views.session),
    re_path(r'^events/([^/]+)/sessions/session/(\d+)(?:-[^/]*)?/slides/(\d+)/.*$', postgresqleu.confreg.views.session_slides),
    re_path(r'^events/([^/]+)/sessions/session/(\d+)(?:-[^/]*)?/card\.(svg|png)$', postgresqleu.confreg.views.session_card),
    re_path(r'^events/([^/]+)/schedule/speaker/(\d+)(?:-[^/]*)?/$', postgresqleu.confreg.views.speaker),
    re_path(r'^events/([^/]+)/sessions/speaker/(\d+)(?:-[^/]*)?/$', postgresqleu.confreg.views.speaker),
    re_path(r'^events/([^/]+)/sessions/speaker/(\d+)(?:-[^/]*)?/card\.(svg|png)$', postgresqleu.confreg.views.speaker_card),
    re_path(r'^events/(?P<urlname>[^/]+)/volunteer/$', postgresqleu.confreg.volsched.volunteerschedule),
    re_path(r'^events/(?P<urlname>[^/]+)/volunteer/api/$', postgresqleu.confreg.volsched.volunteerschedule_api),
    re_path(r'^events/(?P<urlname>[^/]+)/volunteer/ical/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.volsched.ical),
    re_path(r'^events/(?P<urlname>[^/]+)/volunteer/(?P<token>[a-z0-9]{64})/twitter/$', postgresqleu.confreg.twitter.volunteer_twitter),
    re_path(r'^events/([^/]+)/badgescan/$', postgresqleu.confsponsor.scanning.landing),
    re_path(r'^events/([^/]+)/checkin/$', postgresqleu.confreg.checkin.landing),
    re_path(r'^events/([^/]+)/checkin/([a-z0-9]{64})/$', postgresqleu.confreg.checkin.checkin),
    re_path(r'^events/([^/]+)/checkin/([a-z0-9]{64})/api/(\w+)/$', postgresqleu.confreg.checkin.api),
    re_path(r'^events/([^/]+)/checkin/([a-z0-9]{64})/f(\w+)/$', postgresqleu.confreg.checkin.checkin_field),
    re_path(r'^events/([^/]+)/checkin/([a-z0-9]{64})/f(\w+)/api/(\w+)/$', postgresqleu.confreg.checkin.checkin_field_api),
    re_path(r'^events/([^/]+)/sessions/$', postgresqleu.confreg.views.sessionlist),
    re_path(r'^events/speaker/(\d+)/photo/(\d+/)?$', postgresqleu.confreg.views.speakerphoto),
    re_path(r'^events/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
    re_path(r'^events/([^/]+)/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
    re_path(r'^events/([^/]+)/callforpapers/$', postgresqleu.confreg.views.callforpapers),
    re_path(r'^events/([^/]+)/callforpapers/(\d+|new)/$', postgresqleu.confreg.views.callforpapers_edit),
    re_path(r'^events/([^/]+)/callforpapers/copy/$', postgresqleu.confreg.views.callforpapers_copy),
    re_path(r'^events/([^/]+)/callforpapers/(\d+)/delslides/(\d+)/$', postgresqleu.confreg.views.callforpapers_delslides),
    re_path(r'^events/([^/]+)/callforpapers/(\d+)/speakerconfirm/$', postgresqleu.confreg.views.callforpapers_confirm),
    re_path(r'^events/([^/]+)/callforpapers/lookups/speakers/$', postgresqleu.confreg.views.public_speaker_lookup),
    re_path(r'^events/callforpapers/$', postgresqleu.confreg.views.callforpaperslist),
    re_path(r'^events/([^/]+)/register/confirm/$', postgresqleu.confreg.views.confirmreg),
    re_path(r'^events/([^/]+)/register/policy/$', postgresqleu.confreg.views.regconfirmpolicy),
    re_path(r'^events/([^/]+)/register/waitlist_signup/$', postgresqleu.confreg.views.waitlist_signup),
    re_path(r'^events/([^/]+)/register/waitlist_cancel/$', postgresqleu.confreg.views.waitlist_cancel),
    re_path(r'^events/([^/]+)/register/canceled/$', postgresqleu.confreg.views.cancelreg),
    re_path(r'^events/([^/]+)/register/invoice/(\d+)/$', postgresqleu.confreg.views.invoice),
    re_path(r'^events/([^/]+)/register/invoice/(\d+)/cancel/$', postgresqleu.confreg.views.invoice_cancel),
    re_path(r'^events/([^/]+)/register/mail/(\d+)/$', postgresqleu.confreg.views.attendee_mail),
    re_path(r'^events/(?P<confname>[^/]+)/register/(?P<whatfor>(self)/)?addopt/$', postgresqleu.confreg.views.reg_add_options),
    re_path(r'^events/([^/]+)/register/wiki/(.*)/edit/$', postgresqleu.confwiki.views.wikipage_edit),
    re_path(r'^events/([^/]+)/register/wiki/(.*)/history/$', postgresqleu.confwiki.views.wikipage_history),
    re_path(r'^events/([^/]+)/register/wiki/(.*)/sub/$', postgresqleu.confwiki.views.wikipage_subscribe),
    re_path(r'^events/([^/]+)/register/wiki/(.*)/$', postgresqleu.confwiki.views.wikipage),
    re_path(r'^events/([^/]+)/register/signup/(\d+)/$', postgresqleu.confwiki.views.signup),
    re_path(r'^events/([^/]+)/register/signup/(?:.*)-(\d+)/$', postgresqleu.confwiki.views.signup),
    re_path(r'^events/([^/]+)/register/ticket/$', postgresqleu.confreg.views.download_ticket),
    re_path(r'^events/([^/]+)/register/viewticket/$', postgresqleu.confreg.views.view_ticket),
    re_path(r'^events/([^/]+)/\.well-known/jwks\.json', postgresqleu.confreg.api.jwk_json),
    re_path(r'^events/([^/]+)/register/access/', postgresqleu.confreg.api.conference_temp_token),
    re_path(r'^events/([^/]+)/register/token/', postgresqleu.confreg.api.conference_jwt),

    # Opt out of communications
    re_path(r'^events/optout/$', postgresqleu.confreg.views.optout),
    re_path(r'^events/optout/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.views.optout),

    # Backend/admin urls
    re_path(r'^events/admin/$', postgresqleu.confreg.views.admin_dashboard),
    re_path(r'^events/admin/crossmail/$', postgresqleu.confreg.views.crossmail),
    re_path(r'^events/admin/crossmail/(\d+)/$', postgresqleu.confreg.views.crossmail_view),
    re_path(r'^events/admin/crossmail/send/$', postgresqleu.confreg.views.crossmail_send),
    re_path(r'^events/admin/crossmail/options/$', postgresqleu.confreg.views.crossmailoptions),
    re_path(r'^events/admin/reports/time/$', postgresqleu.confreg.reporting.timereport),
    re_path(r'^events/admin/_series/(\d+)/$', postgresqleu.confreg.backendviews.manage_series),
    re_path(r'^events/admin/([^/]+)/reports/$', postgresqleu.confreg.views.reports),
    re_path(r'^events/admin/([^/]+)/reports/simple/$', postgresqleu.confreg.views.simple_report),
    re_path(r'^events/admin/([^/]+)/reports/feedback/$', postgresqleu.confreg.feedback.feedback_report),
    re_path(r'^events/admin/([^/]+)/reports/feedback/session/$', postgresqleu.confreg.feedback.feedback_sessions),
    re_path(r'^events/admin/([^/]+)/reports/schedule/$', postgresqleu.confreg.pdfschedule.pdfschedule),
    re_path(r'^events/admin/newconference/$', postgresqleu.confreg.backendviews.new_conference),
    re_path(r'^events/admin/meta/series/(.*/)?$', postgresqleu.confreg.backendviews.edit_series),
    re_path(r'^events/admin/meta/tshirts/(.*/)?$', postgresqleu.confreg.backendviews.edit_tshirts),
    re_path(r'^events/admin/meta/speakers/(\d+)/merge/$', postgresqleu.confreg.backendviews.merge_speakers),
    re_path(r'^events/admin/meta/speakers/(.*/)?$', postgresqleu.confreg.backendviews.edit_global_speakers),
    re_path(r'^events/admin/lookups/accounts/$', postgresqleu.util.backendlookups.GeneralAccountLookup.lookup),
    re_path(r'^events/admin/lookups/country/$', postgresqleu.util.backendlookups.CountryLookup.lookup),
    re_path(r'^events/admin/lookups/speakers/$', postgresqleu.confreg.backendlookups.SpeakerLookup.lookup),
    re_path(r'^events/admin/(\w+)/$', postgresqleu.confreg.views.admin_dashboard_single),
    re_path(r'^events/admin/(\w+)/edit/$', postgresqleu.confreg.backendviews.edit_conference),
    re_path(r'^events/admin/(\w+)/superedit/$', postgresqleu.confreg.backendviews.superedit_conference),
    re_path(r'^events/admin/(\w+)/lookups/regs/$', postgresqleu.confreg.backendlookups.RegisteredUsersLookup.lookup),
    re_path(r'^events/admin/(\w+)/lookups/regsinc/$', postgresqleu.confreg.backendlookups.RegisteredOrPendingUsersLookup.lookup),
    re_path(r'^events/admin/(\w+)/lookups/tags/$', postgresqleu.confreg.backendlookups.SessionTagLookup.lookup),
    re_path(r'^events/admin/(\w+)/mail/$', postgresqleu.confreg.views.admin_attendeemail),
    re_path(r'^events/admin/(\w+)/mail/send/$', postgresqleu.confreg.views.admin_attendeemail_send),
    re_path(r'^events/admin/(\w+)/mail/(\d+)/$', postgresqleu.confreg.views.admin_attendeemail_view),
    re_path(r'^events/admin/(\w+)/externalmail/$', postgresqleu.confreg.views.admin_send_external_email),
    re_path(r'^events/admin/(\w+)/regdashboard/$', postgresqleu.confreg.views.admin_registration_dashboard),
    re_path(r'^events/admin/(\w+)/regdashboard/list/$', postgresqleu.confreg.views.admin_registration_list),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/$', postgresqleu.confreg.views.admin_registration_single),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/log/$', postgresqleu.confreg.views.admin_registration_log),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/edit/$', postgresqleu.confreg.backendviews.edit_registration),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/cancel/$', postgresqleu.confreg.views.admin_registration_cancel),
    re_path(r'^events/admin/(\w+)/regdashboard/list/multicancel/$', postgresqleu.confreg.views.admin_registration_multicancel),
    re_path(r'^events/admin/(\w+)/regdashboard/list/multiresendwelcome/$', postgresqleu.confreg.views.admin_registration_multiresendwelcome),
    re_path(r'^events/admin/(\w+)/regdashboard/list/multiviewbadge/$', postgresqleu.confreg.backendviews.view_multi_registration_badge),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/confirm/$', postgresqleu.confreg.views.admin_registration_confirm),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/clearcode/$', postgresqleu.confreg.views.admin_registration_clearcode),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/ticket/$', postgresqleu.confreg.backendviews.view_registration_ticket),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/badge/$', postgresqleu.confreg.backendviews.view_registration_badge),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/resendwelcome/$', postgresqleu.confreg.views.admin_registration_resendwelcome),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/resendattach/$', postgresqleu.confreg.views.admin_registration_resendattach),
    re_path(r'^events/admin/(\w+)/regdashboard/list/(\d+)/senddm/$', postgresqleu.confreg.backendviews.registration_dashboard_send_dm),
    re_path(r'^events/admin/(\w+)/regdashboard/list/sendmail/$', postgresqleu.confreg.backendviews.registration_dashboard_send_email),
    re_path(r'^events/admin/(\w+)/prepaid/$', postgresqleu.confreg.views.createvouchers),
    re_path(r'^events/admin/(\w+)/prepaid/list/$', postgresqleu.confreg.views.listvouchers),
    re_path(r'^events/admin/(\w+)/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers),
    re_path(r'^events/admin/(\w+)/prepaid/(\d+)/del/(\d+)/$', postgresqleu.confreg.views.delvouchers),
    re_path(r'^events/admin/(\w+)/prepaid/(\d+)/send_email/$', postgresqleu.confreg.views.emailvouchers),
    re_path(r'^events/admin/(\w+)/prepaidorders/$', postgresqleu.confreg.backendviews.prepaidorders),
    re_path(r'^events/admin/(\w+)/prepaidorders/(\d+)/refund/$', postgresqleu.confreg.backendviews.prepaidorder_refund),
    re_path(r'^events/admin/([^/]+)/schedule/create/$', postgresqleu.confreg.views.createschedule),
    re_path(r'^events/admin/([^/]+)/schedule/create/publish/$', postgresqleu.confreg.views.publishschedule),
    re_path(r'^events/admin/([^/]+)/schedule/jsonschedule/$', postgresqleu.confreg.views.schedulejson),
    re_path(r'^events/admin/([^/]+)/sessionnotifyqueue/$', postgresqleu.confreg.views.session_notify_queue),
    re_path(r'^events/admin/(\w+)/waitlist/$', postgresqleu.confreg.views.admin_waitlist),
    re_path(r'^events/admin/(\w+)/waitlist/offer/$', postgresqleu.confreg.views.admin_waitlist_offer),
    re_path(r'^events/admin/(\w+)/waitlist/cancel/(\d+)/$', postgresqleu.confreg.views.admin_waitlist_cancel),
    re_path(r'^events/admin/(\w+)/waitlist/sendmail/$', postgresqleu.confreg.views.admin_waitlist_sendmail),
    re_path(r'^events/admin/(\w+)/waitlist/sendmail/send/$', postgresqleu.confreg.views.admin_waitlist_sendmail_send),
    re_path(r'^events/admin/(\w+)/wiki/$', postgresqleu.confwiki.views.admin),
    re_path(r'^events/admin/(\w+)/wiki/(new|\d+)/$', postgresqleu.confwiki.views.admin_edit_page),
    re_path(r'^events/admin/(\w+)/wiki/(\d+)/sendmail/$', postgresqleu.confwiki.views.admin_sendmail),
    re_path(r'^events/admin/(\w+)/signups/$', postgresqleu.confwiki.views.signup_admin),
    re_path(r'^events/admin/(\w+)/signups/(new|\d+)/$', postgresqleu.confwiki.views.signup_admin_edit),
    re_path(r'^events/admin/(\w+)/signups/(\d+)/sendmail/$', postgresqleu.confwiki.views.signup_admin_sendmail),
    re_path(r'^events/admin/(\w+)/signups/(\d+)/edit/(new|\d+)/$', postgresqleu.confwiki.views.signup_admin_editsignup),
    re_path(r'^events/admin/(\w+)/transfer/$', postgresqleu.confreg.views.transfer_reg),
    re_path(r'^events/admin/(\w+)/transfer/getaddress/$', postgresqleu.confreg.views.transfer_get_address),
    re_path(r'^events/admin/(\w+)/cancelrequests/$', postgresqleu.confreg.backendviews.cancelrequests),
    re_path(r'^events/admin/(?P<urlname>[^/]+)/volunteer/$', postgresqleu.confreg.volsched.volunteerschedule, {'adm': True}),
    re_path(r'^events/admin/(?P<urlname>[^/]+)/volunteer/api/$', postgresqleu.confreg.volsched.volunteerschedule_api, {'adm': True}),
    re_path(r'^events/admin/(?P<urlname>[^/]+)/volunteer/ical/(?P<token>[a-z0-9]{64})/$', postgresqleu.confreg.volsched.ical, {'adm': True}),
    re_path(r'^events/admin/(\w+)/regdays/(.*/)?$', postgresqleu.confreg.backendviews.edit_regdays),
    re_path(r'^events/admin/(\w+)/regclasses/(.*/)?$', postgresqleu.confreg.backendviews.edit_regclasses),
    re_path(r'^events/admin/(\w+)/regtypes/(.*/)?$', postgresqleu.confreg.backendviews.edit_regtypes),
    re_path(r'^events/admin/(\w+)/addopts/(.*/)?$', postgresqleu.confreg.backendviews.edit_additionaloptions),
    re_path(r'^events/admin/(\w+)/tracks/(.*/)?$', postgresqleu.confreg.backendviews.edit_tracks),
    re_path(r'^events/admin/(\w+)/rooms/(.*/)?$', postgresqleu.confreg.backendviews.edit_rooms),
    re_path(r'^events/admin/(\w+)/tags/(.*/)?$', postgresqleu.confreg.backendviews.edit_tags),
    re_path(r'^events/admin/(\w+)/refundpatterns/(.*/)?$', postgresqleu.confreg.backendviews.edit_refundpatterns),
    re_path(r'^events/admin/(\w+)/sessions/sendmail/$', postgresqleu.confreg.backendviews.conference_session_send_email),
    re_path(r'^events/admin/(\w+)/sessions/(.*/)?$', postgresqleu.confreg.backendviews.edit_sessions),
    re_path(r'^events/admin/(\w+)/speakers/(.*/)?$', postgresqleu.confreg.backendviews.edit_speakers),
    re_path(r'^events/admin/(\w+)/scheduleslots/(.*/)?$', postgresqleu.confreg.backendviews.edit_scheduleslots),
    re_path(r'^events/admin/(\w+)/volunteerslots/(.*/)?$', postgresqleu.confreg.backendviews.edit_volunteerslots),
    re_path(r'^events/admin/(\w+)/feedbackquestions/(.*/)?$', postgresqleu.confreg.backendviews.edit_feedbackquestions),
    re_path(r'^events/admin/(\w+)/discountcodes/(.*/)?$', postgresqleu.confreg.backendviews.edit_discountcodes),
    re_path(r'^events/admin/(\w+)/messaging/(.*/)?$', postgresqleu.confreg.backendviews.edit_messaging),
    re_path(r'^events/admin/(\w+)/accesstokens/(.*/)?$', postgresqleu.confreg.backendviews.edit_accesstokens),
    re_path(r'^events/admin/(\w+)/news/(.*/)?$', postgresqleu.confreg.backendviews.edit_news),
    re_path(r'^events/admin/(\w+)/tweet/queue/(.*/)?$', postgresqleu.confreg.backendviews.edit_tweetqueue),
    re_path(r'^events/admin/(\w+)/tweet/hashtag/(.*/)?$', postgresqleu.confreg.backendviews.edit_hashtags),
    re_path(r'^events/admin/(\w+)/tweet/campaign/$', postgresqleu.confreg.backendviews.tweetcampaignselect),
    re_path(r'^events/admin/(\w+)/tweet/campaign/(\d+)/$', postgresqleu.confreg.backendviews.tweetcampaign),
    re_path(r'^events/admin/(\w+)/pendinginvoices/$', postgresqleu.confreg.backendviews.pendinginvoices),
    re_path(r'^events/admin/(\w+)/pendinginvoices/(\d+)/cancel/$', postgresqleu.confreg.backendviews.pendinginvoices_cancel),
    re_path(r'^events/admin/(\w+)/multiregs/$', postgresqleu.confreg.backendviews.multiregs),
    re_path(r'^events/admin/(\w+)/multiregs/(\d+)/refund/$', postgresqleu.confreg.backendviews.multireg_refund),
    re_path(r'^events/admin/(\w+)/addoptorders/$', postgresqleu.confreg.backendviews.addoptorders),
    re_path(r'^events/admin/(\w+)/paymentstats/$', postgresqleu.confreg.backendviews.paymentstats),
    re_path(r'^events/admin/(\w+)/purgedata/$', postgresqleu.confreg.backendviews.purge_personal_data),
    re_path(r'^events/admin/_series/(\d+)/messaging/(.*/)?$', postgresqleu.confreg.backendviews.edit_series_messaging),
    re_path(r'^events/admin/([^/]+)/talkvote/$', postgresqleu.confreg.views.talkvote),
    re_path(r'^events/admin/([^/]+)/talkvote/changestatus/$', postgresqleu.confreg.views.talkvote_status),
    re_path(r'^events/admin/([^/]+)/talkvote/vote/$', postgresqleu.confreg.views.talkvote_vote),
    re_path(r'^events/admin/([^/]+)/talkvote/comment/$', postgresqleu.confreg.views.talkvote_comment),
    re_path(r'^events/admin/([^/]+)/upload/$', postgresqleu.confreg.upload.index),

    re_path(r'^events/admin/(\w+)/tokendata/([a-z0-9]{64})/(\w+)\.(tsv|csv|json|yaml)(/[^/]+)?$', postgresqleu.confreg.backendviews.tokendata),

    re_path(r'^events/sponsor/', include('postgresqleu.confsponsor.urls')),

    # "Homepage" for events
    re_path(r'^events/([^/]+)/$', postgresqleu.confreg.views.confhome),

    # Legacy event URLs
    re_path(r'^events/(register|feedback|schedule|sessions|talkvote|speakerprofile|callforpapers|reports)/([^/]+)/(.*)?$', postgresqleu.confreg.views.legacy_redirect),


    # Accounts
    re_path(r'^account/$', postgresqleu.account.views.home),

    # Second generation invoice management system
    re_path(r'^invoiceadmin/$', postgresqleu.invoices.views.unpaid),
    re_path(r'^invoiceadmin/unpaid/$', postgresqleu.invoices.views.unpaid),
    re_path(r'^invoiceadmin/paid/$', postgresqleu.invoices.views.paid),
    re_path(r'^invoiceadmin/pending/$', postgresqleu.invoices.views.pending),
    re_path(r'^invoiceadmin/deleted/$', postgresqleu.invoices.views.deleted),
    re_path(r'^invoiceadmin/search/$', postgresqleu.invoices.views.search),
    re_path(r'^invoiceadmin/(\d+)/$', postgresqleu.invoices.views.oneinvoice),
    re_path(r'^invoiceadmin/(new)/$', postgresqleu.invoices.views.oneinvoice),
    re_path(r'^invoiceadmin/(\d+)/flag/$', postgresqleu.invoices.views.flaginvoice),
    re_path(r'^invoiceadmin/(\d+)/cancel/$', postgresqleu.invoices.views.cancelinvoice),
    re_path(r'^invoiceadmin/(\d+)/refund/$', postgresqleu.invoices.views.refundinvoice),
    re_path(r'^invoiceadmin/(\d+)/preview/$', postgresqleu.invoices.views.previewinvoice),
    re_path(r'^invoiceadmin/(\d+)/send_email/$', postgresqleu.invoices.views.emailinvoice),
    re_path(r'^invoiceadmin/(\d+)/extend_cancel/$', postgresqleu.invoices.views.extend_cancel),
    re_path(r'^invoices/(\d+)/$', postgresqleu.invoices.views.viewinvoice),
    re_path(r'^invoices/(\d+)/pdf/$', postgresqleu.invoices.views.viewinvoicepdf),
    re_path(r'^invoices/(\d+)/receipt/$', postgresqleu.invoices.views.viewreceipt),
    re_path(r'^invoices/(\d+)/refundnote/(\d+)/$', postgresqleu.invoices.views.viewrefundnote),
    re_path(r'^invoices/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.viewinvoice_secret),
    re_path(r'^invoices/(\d+)/([a-z0-9]{64})/pdf/$', postgresqleu.invoices.views.viewinvoicepdf_secret),
    re_path(r'^invoices/(\d+)/([a-z0-9]{64})/receipt/$', postgresqleu.invoices.views.viewreceipt_secret),
    re_path(r'^invoices/(\d+)/([a-z0-9]{64})/refundnote/(\d+)/$', postgresqleu.invoices.views.viewrefundnote_secret),
    re_path(r'^invoices/dummy/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.dummy_payment),
    re_path(r'^invoices/$', postgresqleu.invoices.views.userhome),
    re_path(r'^invoices/banktransfer/$', postgresqleu.invoices.views.banktransfer),
    re_path(r'^invoices/adyenpayment/(\d+)/(\d+)/(return/|iban/)?$', postgresqleu.adyen.views.invoicepayment),
    re_path(r'^invoices/adyenpayment/(\d+)/(\d+)/(\w+)/(return/|iban/)?$', postgresqleu.adyen.views.invoicepayment_secret),
    re_path(r'^invoices/adyen_bank/(\d+)/(\d+)/$', postgresqleu.adyen.views.bankpayment),
    re_path(r'^invoices/adyen_bank/(\d+)/(\d+)/(\w+)/$', postgresqleu.adyen.views.bankpayment_secret),
    re_path(r'^admin/invoices/vatrates/(.*/)?$', postgresqleu.invoices.backendviews.edit_vatrate),
    re_path(r'^admin/invoices/vatcache/(.*/)?$', postgresqleu.invoices.backendviews.edit_vatvalidationcache),
    re_path(r'^admin/invoices/refunds/$', postgresqleu.invoices.backendviews.refunds),
    re_path(r'^admin/invoices/refundexposure/$', postgresqleu.invoices.backendviews.refundexposure),
    re_path(r'^admin/invoices/banktransactions/$', postgresqleu.invoices.backendviews.banktransactions),
    re_path(r'^admin/invoices/banktransactions/(\d+)/$', postgresqleu.invoices.backendviews.banktransactions_match),
    re_path(r'^admin/invoices/banktransactions/(\d+)/(\d+)/$', postgresqleu.invoices.backendviews.banktransactions_match_invoice),
    re_path(r'^admin/invoices/banktransactions/(\d+)/multimatch/$', postgresqleu.invoices.backendviews.banktransactions_match_multiple),
    re_path(r'^admin/invoices/banktransactions/(\d+)/m(\d+)/$', postgresqleu.invoices.backendviews.banktransactions_match_matcher),
    re_path(r'^admin/invoices/banktransactions/multiple/$', postgresqleu.invoices.backendviews.banktransactions_multi_to_one),
    re_path(r'^admin/invoices/bankfiles/$', postgresqleu.invoices.backendviews.bankfiles),
    re_path(r'^admin/invoices/bankfiles/transactions/$', postgresqleu.invoices.backendviews.bankfile_transaction_methodchoice),
    re_path(r'^admin/invoices/bankfiles/transactions/(\d+)/$', postgresqleu.invoices.backendviews.bankfile_transactions),
    re_path(r'^admin/invoices/paymentmethods/(\d+)/plaidconnect/$', postgresqleu.plaid.backendviews.connect_to_plaid),
    re_path(r'^admin/invoices/paymentmethods/(\d+)/refreshplaidconnect/$', postgresqleu.plaid.backendviews.refresh_plaid_connect),
    re_path(r'^admin/invoices/paymentmethods/(\d+)/gocardlessconnect/$', postgresqleu.gocardless.backendviews.connect_to_gocardless),
    re_path(r'^admin/invoices/paymentmethods/(.*/)?$', postgresqleu.invoices.backendviews.edit_paymentmethod),
    re_path(r'^invoices/trustlypay/(\d+)/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.invoicepayment_secret),
    re_path(r'^trustly_notification/(\d+)/$', postgresqleu.trustlypayment.views.notification),
    re_path(r'^trustly_success/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.success),
    re_path(r'^trustly_failure/(\d+)/(\w+)/$', postgresqleu.trustlypayment.views.failure),
    re_path(r'^invoices/braintree/(\d+)/(\d+)/$', postgresqleu.braintreepayment.views.invoicepayment),
    re_path(r'^invoices/braintree/(\d+)/(\d+)/(\w+)/$', postgresqleu.braintreepayment.views.invoicepayment_secret),
    re_path(r'^p/braintree/$', postgresqleu.braintreepayment.views.payment_post),
    re_path(r'^invoices/stripepay/(\d+)/(\d+)/(\w+)/$', postgresqleu.stripepayment.views.invoicepayment_secret),
    re_path(r'^invoices/stripepay/(\d+)/(\d+)/(\w+)/results/$', postgresqleu.stripepayment.views.invoicepayment_results),
    re_path(r'^invoices/stripepay/(\d+)/(\d+)/(\w+)/cancel/$', postgresqleu.stripepayment.views.invoicepayment_cancel),
    re_path(r'^p/stripe/(\d+)/webhook/', postgresqleu.stripepayment.views.webhook),

    # Basic accounting system
    re_path(r'^accounting/$', postgresqleu.accounting.views.index),
    re_path(r'^accounting/(\d+)/$', postgresqleu.accounting.views.year),
    re_path(r'^accounting/e/(\d+)/$', postgresqleu.accounting.views.entry),
    re_path(r'^accounting/(\d+)/new/$', postgresqleu.accounting.views.new),
    re_path(r'^accounting/(\d+)/close/$', postgresqleu.accounting.views.closeyear),
    re_path(r'^accounting/([\d-]+)/report/(\w+)/$', postgresqleu.accounting.views.report),
    re_path(r'^admin/accounting/accountstructure/$', postgresqleu.accounting.backendviews.accountstructure),
    re_path(r'^admin/accounting/accountclasses/(.*/)?$', postgresqleu.accounting.backendviews.edit_accountclass),
    re_path(r'^admin/accounting/accountgroups/(.*/)?$', postgresqleu.accounting.backendviews.edit_accountgroup),
    re_path(r'^admin/accounting/accounts/(.*/)?$', postgresqleu.accounting.backendviews.edit_account),
    re_path(r'^admin/accounting/objects/(.*/)?$', postgresqleu.accounting.backendviews.edit_object),

    # Scheduled jobs
    re_path(r'^admin/jobs/$', postgresqleu.scheduler.views.index),
    re_path(r'^admin/jobs/(\d+)/$', postgresqleu.scheduler.views.job),
    re_path(r'^admin/jobs/history/$', postgresqleu.scheduler.views.history),

    # Digial signatures
    re_path(r'^admin/digisign/providers/(\d+)/log/$', postgresqleu.digisign.backendviews.view_provider_log),
    re_path(r'^admin/digisign/providers/(\d+)/log/(\d+)/$', postgresqleu.digisign.backendviews.view_provider_log_details),
    re_path(r'^admin/digisign/providers/(.*/)?$', postgresqleu.digisign.backendviews.edit_providers),

    # Mail queue
    re_path(r'^admin/mailqueue/(\d+)/attachments/(.+)/$', postgresqleu.mailqueue.backendviews.view_attachment),
    re_path(r'^admin/mailqueue/(.*/)?$', postgresqleu.mailqueue.backendviews.edit_mailqueue),

    # Tokens (QR codes scanned)
    re_path(r'^t/id/([a-z0-9]+|TESTTESTTESTTEST)/$', postgresqleu.confreg.checkin.checkin_token),
    re_path(r'^t/at/(?P<scanned_token>[a-z0-9]+|TESTTESTTESTTEST)/(?P<what>\w+/)?$', postgresqleu.confreg.checkin.badge_token),

    # Webhooks for messaging
    re_path(r'^wh/(\d+)/([a-z0-9]+)/$', postgresqleu.util.views.messaging_webhook),
    re_path(r'^wh/twitter/', postgresqleu.util.views.twitter_webhook),

    # Handle paypal data returns
    re_path(r'^p/paypal_return/(\d+)/$', postgresqleu.paypal.views.paypal_return_handler),

    # Handle adyen data returns
    re_path(r'^p/adyen_notify/(\d+)/$', postgresqleu.adyen.views.adyen_notify_handler),

    # Transferwise webhooks
    re_path(r'^wh/tw/(\d+)/(\w+)/$', postgresqleu.transferwise.views.webhook),

    # Plaid webhooks
    re_path(r'^wh/plaid/(\d+)/$', postgresqleu.plaid.views.webhook),

    # Digital signatures webhooks
    re_path(r'^wh/(sw)/(\d+)/$', postgresqleu.digisign.views.webhook),

    # Account info callbacks
    re_path(r'^accountinfo/search/$', postgresqleu.accountinfo.views.search),
    re_path(r'^accountinfo/import/$', postgresqleu.accountinfo.views.importuser),

    # OAuth application registry
    re_path(r'^admin/oauthapps/(.*/)?$', postgresqleu.util.backendviews.edit_oauthapps),
    re_path(r'^oauth_return/messaging/(\d+/)?$', postgresqleu.util.views.oauth_return),

    # Monitoring endpoints
    re_path(r'^monitor/git/$', postgresqleu.util.monitor.gitinfo),
    re_path(r'^monitor/nagios/$', postgresqleu.util.monitor.nagios),

    # Digital assets needed to do deep-linking in the android app.
    re_path(r'^.well-known/assetlinks.json$', postgresqleu.util.views.assetlinks),
])

if settings.ENABLE_NEWS:
    urlpatterns.extend([
        re_path(r'^news/archive/$', postgresqleu.newsevents.views.newsarchive),
        re_path(r'^news/[^/]+-(\d+)/$', postgresqleu.newsevents.views.newsitem),
        re_path(r'^events/([^/]+)/news/$', postgresqleu.confreg.views.news_index),
        re_path(r'^events/([^/]+)/news/[^/]+-(\d+)/$', postgresqleu.confreg.views.news_page),

        # Feeds
        re_path(r'^feeds/(?P<what>(news|user/[^/]+))/$', LatestNews()),
        re_path(r'^feeds/conf/(?P<what>[^/]+)/$', ConferenceNewsFeed()),
        re_path(r'^feeds/conf/(?P<confname>[^/]+)/json/$', postgresqleu.confreg.views.news_json),
        re_path(r'^feeds/conf/(?P<confname>[^/]+)/image/(?P<postid>\d+)/$', postgresqleu.confreg.views.news_post_image),
    ])

if settings.ENABLE_MEMBERSHIP:
    import postgresqleu.membership.views
    import postgresqleu.membership.backendviews
    urlpatterns.extend([
        # Membership management
        re_path(r'^membership/$', postgresqleu.membership.views.home),
        re_path(r'^membership/mail/(\d+)/$', postgresqleu.membership.views.mail),
        re_path(r'^membership/meetings/$', postgresqleu.membership.views.meetings),
        re_path(r'^membership/meetings/(\d+)/$', postgresqleu.membership.views.meeting),
        re_path(r'^membership/meetings/(\d+)/ical/$', postgresqleu.membership.views.meeting_ical),
        re_path(r'^membership/meetings/(\d+)/([a-z0-9]{64})/$', postgresqleu.membership.views.meeting_by_key),
        re_path(r'^membership/meetings/(\d+)/proxy/$', postgresqleu.membership.views.meeting_proxy),
        re_path(r'^membership/meetings/(\d+)/join/$', postgresqleu.membership.views.webmeeting),
        re_path(r'^membership/meetings/(\d+)/([a-z0-9]{64})/join/$', postgresqleu.membership.views.webmeeting_by_key),
        re_path(r'^membership/meetingcode/$', postgresqleu.membership.views.meetingcode),
        re_path(r'^membership/members/$', postgresqleu.membership.views.userlist),
        re_path(r'^admin/membership/config/$', postgresqleu.membership.backendviews.edit_config),
        re_path(r'^admin/membership/members/sendmail/$', postgresqleu.membership.backendviews.sendmail),
        re_path(r'^admin/membership/members/(.*/)?$', postgresqleu.membership.backendviews.edit_member),
        re_path(r'^admin/membership/meetings/(\d+)/log/$', postgresqleu.membership.backendviews.meeting_log),
        re_path(r'^admin/membership/meetings/(\d+)/attendees/$', postgresqleu.membership.backendviews.meeting_attendees),
        re_path(r'^admin/membership/meetings/serverstatus/$', postgresqleu.membership.backendviews.meetingserverstatus),
        re_path(r'^admin/membership/meetings/(.*/)?$', postgresqleu.membership.backendviews.edit_meeting),
        re_path(r'^admin/membership/emails/$', postgresqleu.membership.backendviews.member_email_list),
        re_path(r'^admin/membership/emails/(\d+)/$', postgresqleu.membership.backendviews.member_email),
        re_path(r'^admin/membership/lookups/member/$', postgresqleu.membership.backendlookups.MemberLookup.lookup),
    ])

if settings.ENABLE_ELECTIONS:
    import postgresqleu.elections.views
    import postgresqleu.elections.backendviews
    urlpatterns.extend([
        # Elections
        re_path(r'^elections/$', postgresqleu.elections.views.home),
        re_path(r'^elections/(\d+)/$', postgresqleu.elections.views.election),
        re_path(r'^elections/(\d+)/candidate/(\d+)/$', postgresqleu.elections.views.candidate),
        re_path(r'^elections/(\d+)/ownvotes/$', postgresqleu.elections.views.ownvotes),
        re_path(r'^admin/elections/election/(.*/)?$', postgresqleu.elections.backendviews.edit_election),
    ])

if settings.DEBUG_TOOLBAR:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns


# Now extend with some fallback URLs as well
urlpatterns.extend([
    # Admin site
    re_path(r'^admin/django/', admin.site.urls),

    # Fallback - send everything nonspecific to the static handler
    re_path(r'^(.*)/$', postgresqleu.static.views.static_fallback),
])
