from django.contrib import admin

from postgresqleu.util.forms import ConcurrentProtectedModelForm

from postgresqleu.newsevents.models import News, NewsPosterProfile


class NewsPosterProfileAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'rsslink')
    autocomplete_fields = ('author', )

    def rsslink(self, author):
        return "/feeds/user/{0}/".format(author.urlname)


admin.site.register(News)
admin.site.register(NewsPosterProfile, NewsPosterProfileAdmin)
