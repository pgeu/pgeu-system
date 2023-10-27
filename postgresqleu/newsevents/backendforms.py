import django.forms
from django.contrib.auth.models import User

from postgresqleu.util.backendforms import BackendForm, BackendBeforeNewForm
from postgresqleu.util.fields import UserModelChoiceField
from postgresqleu.newsevents.models import News, NewsPosterProfile
from postgresqleu.confreg.backendforms import BackendTweetQueueForm


class BackendNewsForm(BackendForm):
    list_fields = ['datetime', 'title', 'author', ]
    queryset_select_related = ['author', ]
    markdown_fields = ['summary', ]

    class Meta:
        model = News
        fields = ['title', 'datetime', 'author', 'summary', 'highpriorityuntil',
                  'inrss', 'inarchive', ]

    @classmethod
    def get_column_filters(cls, conference):
        return {
            'Author': NewsPosterProfile.objects.all(),
        }


class BackendNewAuthorForm(BackendBeforeNewForm):
    helplink = 'news#authors'
    user = UserModelChoiceField(queryset=User.objects.order_by('username'))
    selectize_single_fields = {
        'user': None,
    }

    def get_newform_data(self):
        return self.cleaned_data['user'].pk


class BackendAuthorForm(BackendForm):
    list_fields = ['author', 'fullname', 'urlname', 'canpostglobal', ]
    form_before_new = BackendNewAuthorForm

    class Meta:
        model = NewsPosterProfile
        fields = ['fullname', 'urlname', 'canpostglobal', ]

    def fix_fields(self):
        if self.newformdata:
            self.instance.author = User.objects.get(pk=self.newformdata)
            # We must force the system to do an insert at this point. Since we set 'pk',
            # it will otherwise think it's an edit, do an UPDATE, and fail.
            self.force_insert = True


class BackendPostQueueForm(BackendTweetQueueForm):
    verbose_name = 'news social media post'
    verbose_name_plural = 'news social media posts'
