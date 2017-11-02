import types

from django.contrib import admin

from postgresqleu.util.forms import ConcurrentProtectedModelForm

#
# Inject the ConcurrentProjectedModelForm into all ModelAdmins that don't
# explicitly specify override it. Do this by patching out the meaning
# of admin.ModelAdmin to be our own form which inherits from it.
#
class ConcurrentInjectedAdmin(admin.ModelAdmin):
	form = ConcurrentProtectedModelForm

admin.ModelAdmin = ConcurrentInjectedAdmin



#
# Define our own handling of registering a model for admin without
# it's own class. The default is to set admin_class to ModelAdmin
# in that case, so we just do it one step early in order to use our
# own injected model from above.
#
_oldreg = admin.site.register
def _concurrent_injected_register(self, model_or_iterable, admin_class=None, **options):
	if admin_class is None:
		admin_class = ConcurrentInjectedAdmin
	return _oldreg(model_or_iterable, admin_class, **options)

admin.site.register = types.MethodType(_concurrent_injected_register, admin.AdminSite)

