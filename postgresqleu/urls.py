from django.conf.urls.defaults import *
from django.contrib import admin
from django.views.generic.simple import redirect_to

import postgresqleu.static.views
import postgresqleu.newsevents.views
import postgresqleu.views
import postgresqleu.confreg.views
import postgresqleu.confreg.reporting
import postgresqleu.confreg.mobileviews
import postgresqleu.confreg.feedback
import postgresqleu.membership.views
import postgresqleu.elections.views
import postgresqleu.invoicemgr.views
import postgresqleu.invoices.views
import postgresqleu.accounting.views
import postgresqleu.paypal.views
import postgresqleu.adyen.views
import postgresqleu.accountinfo.views

from postgresqleu.newsevents.feeds import LatestNews, LatestEvents

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
admin.autodiscover()


urlpatterns = patterns('',
	# Frontpage
	(r'^$', postgresqleu.views.index),

	# Log in/log out
	(r'^login/?$', 'postgresqleu.auth.login'),
	(r'^logout/?$', 'postgresqleu.auth.logout'),
	(r'^accounts/login/$', 'postgresqleu.auth.login'),
	(r'^accounts/logout/$', 'postgresqleu.auth.logout'),
    (r'^auth_receive/$', 'postgresqleu.auth.auth_receive'),

	# News & Events
	(r'^events$', postgresqleu.newsevents.views.eventlist),
	(r'^events/(\d+)$', postgresqleu.newsevents.views.event),
	(r'^events/archive$', postgresqleu.newsevents.views.eventarchive),

	# Feeds
    (r'^feeds/news/$', LatestNews()),
    (r'^feeds/events/$', LatestEvents()),

	# Conference registration
	(r'^events/register/([^/]+)/$', postgresqleu.confreg.views.home),
	(r'^events/bulkpay/([^/]+)/$', postgresqleu.confreg.views.bulkpay),
	(r'^events/bulkpay/([^/]+)/(\d+)/$', postgresqleu.confreg.views.bulkpay_view),

	(r'^events/feedback/([^/]+)/$', postgresqleu.confreg.views.feedback),
	(r'^events/feedback/([^/]+)/(\d+)/$', postgresqleu.confreg.views.feedback_session),
	(r'^events/feedback/([^/]+)/conference/$', postgresqleu.confreg.views.feedback_conference),
	(r'^events/feedback/$', postgresqleu.confreg.views.feedback_available),
	(r'^events/schedule/([^/]+)/$', postgresqleu.confreg.views.schedule),
	(r'^events/schedule/([^/]+)/ical/$', postgresqleu.confreg.views.schedule_ical),
	(r'^events/schedule/([^/]+)/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	(r'^events/sessions/([^/]+)/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	(r'^events/schedule/([^/]+)/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	(r'^events/sessions/([^/]+)/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	(r'^events/schedule/([^/]+)/create/$', postgresqleu.confreg.views.createschedule),
	(r'^events/schedule/([^/]+)/create/publish/$', postgresqleu.confreg.views.publishschedule),
	(r'^events/talkvote/([^/]+)/$', postgresqleu.confreg.views.talkvote),
    (r'^events/reports/time/$', postgresqleu.confreg.reporting.timereport),
	(r'^events/sessions/([^/]+)/$', postgresqleu.confreg.views.sessionlist),
	(r'^events/speaker/(\d+)/photo/$', postgresqleu.confreg.views.speakerphoto),
	(r'^events/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
	(r'^events/speakerprofile/(\w+)/$', postgresqleu.confreg.views.speakerprofile),
	(r'^events/callforpapers/(\w+)/$', postgresqleu.confreg.views.callforpapers),
	(r'^events/callforpapers/(\w+)/new/$', postgresqleu.confreg.views.callforpapers_new),
	(r'^events/callforpapers/(\w+)/(\d+)/$', postgresqleu.confreg.views.callforpapers_edit),
	(r'^events/callforpapers/(\w+)/(\d+)/speakerconfirm/$', postgresqleu.confreg.views.callforpapers_confirm),
	(r'^events/register/(\w+)/confirm/$', postgresqleu.confreg.views.confirmreg),
	(r'^events/register/(\w+)/canceled/$', postgresqleu.confreg.views.cancelreg),
	(r'^events/register/(\w+)/invoice/(\d+)/$', postgresqleu.confreg.views.invoice),
	(r'^events/prepaid/$', postgresqleu.confreg.views.createvouchers),
	(r'^events/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers),
	(r'^events/prepaid/(\d+)/send_email/$', 'postgresqleu.confreg.views.emailvouchers'),
    (r'^events/reports/(\w+)/$', postgresqleu.confreg.views.reports),
    (r'^events/reports/(\w+)/simple/$', postgresqleu.confreg.views.simple_report),
    (r'^events/reports/(\w+)/advanced/$', postgresqleu.confreg.views.advanced_report),
    (r'^events/reports/(\w+)/feedback/$', postgresqleu.confreg.feedback.feedback_report),
    (r'^events/reports/(\w+)/feedback/session/$', postgresqleu.confreg.feedback.feedback_sessions),
    (r'^events/admin/$', 'postgresqleu.confreg.views.admin_dashboard'),

    # Mobile conference stuff
    (r'^m/(\w+)/$', postgresqleu.confreg.mobileviews.index),
    (r'^m/(\w+)/cache.manifest/$', postgresqleu.confreg.mobileviews.cachemanifest),
    (r'^m/(\w+)/cdj/(\d+)?$', postgresqleu.confreg.mobileviews.conferencedata),
    (r'^m/(\w+)/newsj/$', postgresqleu.confreg.mobileviews.newsproxy),


    # Conference admin
    (r'^admin/confreg/_email/$', 'postgresqleu.confreg.views.admin_email'),
    (r'^admin/confreg/_email_session_speaker/([,\d]+)/$', 'postgresqleu.confreg.views.admin_email_session'),

	# Membership management
	(r'^membership/$', postgresqleu.membership.views.home),
	(r'^community/members/$', postgresqleu.membership.views.userlist),
	(r'^admin/membership/_email/$', 'postgresqleu.membership.views.admin_email'),

	# Merchandise redirect
	(r'^merchandise/', redirect_to, {'url': 'http://postgresqleu.spreadshirt.net/'}),

	# Elections
	(r'^elections/$', postgresqleu.elections.views.home),
	(r'^elections/(\d+)/$', postgresqleu.elections.views.election),
	(r'^elections/(\d+)/candidate/(\d+)/$', postgresqleu.elections.views.candidate),
	(r'^elections/(\d+)/ownvotes/$', postgresqleu.elections.views.ownvotes),

	# Invoice manager (admins only!)
	(r'invoicemgr/$', postgresqleu.invoicemgr.views.home),
	(r'invoicemgr/(\d+)/$', postgresqleu.invoicemgr.views.invoice),
	(r'invoicemgr/(\d+)/pdf/$', postgresqleu.invoicemgr.views.invoicepdf),

    # Second generation invoice management system
    (r'^invoiceadmin/$', postgresqleu.invoices.views.home),
    (r'^invoiceadmin/unpaid/$', postgresqleu.invoices.views.unpaid),
    (r'^invoiceadmin/pending/$', postgresqleu.invoices.views.pending),
    (r'^invoiceadmin/deleted/$', postgresqleu.invoices.views.deleted),
    (r'^invoiceadmin/refunded/$', postgresqleu.invoices.views.refunded),
    (r'^invoiceadmin/search/$', postgresqleu.invoices.views.search),
    (r'^invoiceadmin/(\d+)/$', postgresqleu.invoices.views.oneinvoice),
    (r'^invoiceadmin/(new)/$', postgresqleu.invoices.views.oneinvoice),
    (r'^invoiceadmin/(\d+)/flag/$', postgresqleu.invoices.views.flaginvoice),
    (r'^invoiceadmin/(\d+)/cancel/$', postgresqleu.invoices.views.cancelinvoice),
    (r'^invoiceadmin/(\d+)/refund/$', postgresqleu.invoices.views.refundinvoice),
    (r'^invoiceadmin/(\d+)/preview/$', postgresqleu.invoices.views.previewinvoice),
    (r'^invoiceadmin/(\d+)/send_email/$', postgresqleu.invoices.views.emailinvoice),
    (r'^invoices/(\d+)/$', postgresqleu.invoices.views.viewinvoice),
    (r'^invoices/(\d+)/pdf/$', postgresqleu.invoices.views.viewinvoicepdf),
    (r'^invoices/(\d+)/receipt/$', postgresqleu.invoices.views.viewreceipt),
    (r'^invoices/(\d+)/([a-z0-9]{64})/$', postgresqleu.invoices.views.viewinvoice_secret),
    (r'^invoices/(\d+)/([a-z0-9]{64})/pdf/$', postgresqleu.invoices.views.viewinvoicepdf_secret),
    (r'^invoices/(\d+)/([a-z0-9]{64})/receipt/$', postgresqleu.invoices.views.viewreceipt_secret),
    (r'^invoices/$', postgresqleu.invoices.views.userhome),
    (r'^invoices/banktransfer/$', postgresqleu.invoices.views.banktransfer),

    # Basic accounting system
    (r'^accounting/$', postgresqleu.accounting.views.index),
    (r'^accounting/(\d+)/$', postgresqleu.accounting.views.year),
    (r'^accounting/e/(\d+)/$', postgresqleu.accounting.views.entry),
    (r'^accounting/(\d+)/new/$', postgresqleu.accounting.views.new),
    (r'^accounting/(\d+)/close/$', postgresqleu.accounting.views.closeyear),
    (r'^accounting/(\d+)/report/(\w+)/$', postgresqleu.accounting.views.report),

    # Handle paypal data returns
    (r'^p/paypal_return/$', postgresqleu.paypal.views.paypal_return_handler),

    # Handle adyen data returns
    (r'^p/adyen_return/$', postgresqleu.adyen.views.adyen_return_handler),
    (r'^p/adyen_notify/$', postgresqleu.adyen.views.adyen_notify_handler),

    # Account info callbacks
    (r'^accountinfo/search/$', postgresqleu.accountinfo.views.search),

	# This should not happen in production - serve by apache!
	url(r'^(favicon.ico)$', 'django.views.static.serve', {
		'document_root': '../media',
	}),

	# Admin site
    (r'^admin/', include(admin.site.urls)),

	# Fallback - send everything nonspecific to the static handler
	(r'^(.*)/$', postgresqleu.static.views.static_fallback),
)
