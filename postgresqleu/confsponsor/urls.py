from django.conf.urls.defaults import patterns

import views

# All urls already start with /events/sponsor/
urlpatterns = patterns('',
   (r'^$', views.sponsor_dashboard),
   (r'^(\d+)/$', views.sponsor_conference),
   (r'^(\d+)/claim/(\d+)/$', views.sponsor_claim_benefit),
   (r'^(\d+)/managers/add/$', views.sponsor_manager_add),
   (r'^(\d+)/managers/del/$', views.sponsor_manager_delete),
   (r'^(\d+)/viewmail/(\d+)/$', views.sponsor_view_mail),
   (r'^signup/(\w+)/$', views.sponsor_signup_dashboard),
   (r'^signup/(\w+)/(\w+)/$', views.sponsor_signup),
   (r'^viewcontract/(\d+)/$', views.sponsor_contract),
   (r'^admin/imageview/(\d+)/$', views.sponsor_admin_imageview),
   (r'^admin/(\w+)/$', views.sponsor_admin_dashboard),
   (r'^admin/(\w+)/(\d+)/$', views.sponsor_admin_sponsor),
   (r'^admin/(\w+)/(\d+)/generateinvoice/$', views.sponsor_admin_generateinvoice),
   (r'^admin/(\w+)/benefit/(\d+)/$', views.sponsor_admin_benefit),
   (r'^admin/(\w+)/sendmail/$', views.sponsor_admin_send_mail),
   (r'^admin/(\w+)/viewmail/(\d+)/$', views.sponsor_admin_view_mail),
)
