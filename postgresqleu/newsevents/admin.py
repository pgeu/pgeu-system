from django.contrib import admin

from selectable.forms.widgets import AutoCompleteSelectWidget

from postgresqleu.accountinfo.lookups import UserLookup
from postgresqleu.util.forms import ConcurrentProtectedModelForm
from postgresqleu.util.admin import SelectableWidgetAdminFormMixin

from postgresqleu.newsevents.models import News, NewsPosterProfile

class NewsPosterProfileForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = NewsPosterProfile
		exclude = []
		widgets = {
			'author': AutoCompleteSelectWidget(lookup_class=UserLookup),
		}

class NewsPosterProfileAdmin(admin.ModelAdmin):
	form = NewsPosterProfileForm
	list_display = ('__unicode__', 'rsslink')

	def rsslink(self, author):
		return "/feeds/user/{0}/".format(author.urlname)

admin.site.register(News)
admin.site.register(NewsPosterProfile, NewsPosterProfileAdmin)
