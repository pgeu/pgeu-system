from django.conf.urls import url

import views
import backendviews

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
    url(r'^signup/(\w+)/$', views.sponsor_signup_dashboard),
    url(r'^signup/(\w+)/(\w+)/$', views.sponsor_signup),
    url(r'^viewcontract/(\d+)/$', views.sponsor_contract),
    url(r'^admin/imageview/(\d+)/$', views.sponsor_admin_imageview),
    url(r'^admin/(\w+)/$', views.sponsor_admin_dashboard),
    url(r'^admin/(\w+)/(\d+)/$', views.sponsor_admin_sponsor),
    url(r'^admin/(\w+)/(\d+)/edit/$', backendviews.edit_sponsor),
    url(r'^admin/(\w+)/(\d+)/confirm/$', views.sponsor_admin_confirm),
    url(r'^admin/(\w+)/benefit/(\d+)/$', views.sponsor_admin_benefit),
    url(r'^admin/(\w+)/sendmail/$', views.sponsor_admin_send_mail),
    url(r'^admin/(\w+)/viewmail/(\d+)/$', views.sponsor_admin_view_mail),
    url(r'^admin/(\w+)/testvat/$', views.sponsor_admin_test_vat),
    url(r'^admin/(\w+)/levels/(.*/)?$', backendviews.edit_sponsorship_levels),
    url(r'^admin/(\w+)/contracts/(.*/)?$', backendviews.edit_sponsorship_contracts),
]
