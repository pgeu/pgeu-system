from django.conf.urls import url

from . import views
from . import backendviews
from . import scanning

# All urls already start with /events/sponsor/
urlpatterns = [
    url(r'^$', views.sponsor_dashboard),
    url(r'^(\d+)/$', views.sponsor_conference),
    url(r'^(\d+)/claim/(\d+)/$', views.sponsor_claim_benefit),
    url(r'^(\d+)/managers/add/$', views.sponsor_manager_add),
    url(r'^(\d+)/managers/del/$', views.sponsor_manager_delete),
    url(r'^(\d+)/viewmail/(\d+)/$', views.sponsor_view_mail),
    url(r'^(\d+)/purchase/voucher/$', views.sponsor_purchase_voucher),
    url(r'^(\d+)/purchase/discountcode/$', views.sponsor_purchase_discount),
    url(r'^(\d+)/shipments/new/$', views.sponsor_shipment_new),
    url(r'^(\d+)/shipments/(\d+)/$', views.sponsor_shipment),
    url(r'^(\d+)/scanning/$', scanning.sponsor_scanning),
    url(r'^(\d+)/scanning/download.csv/$', scanning.sponsor_scanning_download),
    url(r'^scanning/([a-z0-9]{64})/$', scanning.scanning_page),
    url(r'^scanning/([a-z0-9]{64})/api/$', scanning.scanning_api),
    url(r'^scanning/test/$', scanning.testcode),
    url(r'^signup/(\w+)/$', views.sponsor_signup_dashboard),
    url(r'^signup/(\w+)/(\w+)/$', views.sponsor_signup),
    url(r'^viewcontract/(\d+)/$', views.sponsor_contract),
    url(r'^shipments/([a-z0-9]+)/$', views.sponsor_shipment_receiver),
    url(r'^shipments/([a-z0-9]+)/(\d+)/$', views.sponsor_shipment_receiver_shipment),
    url(r'^admin/imageview/(\d+)/$', views.sponsor_admin_imageview),
    url(r'^admin/(\w+)/$', views.sponsor_admin_dashboard),
    url(r'^admin/(\w+)/(\d+)/$', views.sponsor_admin_sponsor),
    url(r'^admin/(\w+)/(\d+)/edit/$', backendviews.edit_sponsor),
    url(r'^admin/(\w+)/benefit/(\d+)/$', views.sponsor_admin_benefit),
    url(r'^admin/(\w+)/sendmail/$', views.sponsor_admin_send_mail),
    url(r'^admin/(\w+)/viewmail/(\d+)/$', views.sponsor_admin_view_mail),
    url(r'^admin/(\w+)/testvat/$', views.sponsor_admin_test_vat),
    url(r'^admin/(\w+)/levels/(.*/)?$', backendviews.edit_sponsorship_levels),
    url(r'^admin/(\w+)/contracts/(.*/)?$', backendviews.edit_sponsorship_contracts),
    url(r'^admin/(\w+)/addresses/(.*/)?$', backendviews.edit_shipment_addresses),
    url(r'^admin/(\w+)/shipments/new/$', views.admin_shipment_new),
    url(r'^admin/(\w+)/shipments/(\d+)/$', views.admin_shipment),
    url(r'^admin/(\w+)/badgescanstatus/$', scanning.admin_scan_status),
]
