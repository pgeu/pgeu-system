from django.contrib import admin
from django.http import HttpResponseRedirect
from django.forms.models import BaseInlineFormSet
from django.forms.utils import ErrorList
from django.urls import reverse
from django.utils.safestring import mark_safe

from postgresqleu.util.forms import ConcurrentProtectedModelForm

from .models import SponsorshipContract, SponsorshipLevel, Sponsor
from .models import SponsorshipBenefit, SponsorClaimedBenefit

from .benefits import get_benefit_class


class SponsorshipBenefitInlineFormset(BaseInlineFormSet):
    def clean(self):
        for f in self.forms:
            if f.cleaned_data.get('benefit_class') >= 0:
                params = f.cleaned_data.get('class_parameters')
                benefit = get_benefit_class(f.cleaned_data.get('benefit_class'))(self.instance, params)
                if not params:
                    f.cleaned_data['class_parameters'] = {}
                    f.instance.class_parameters = {}
                    params = {}


class SponsorshipBenefitInline(admin.TabularInline):
    model = SponsorshipBenefit
    extra = 1
    formset = SponsorshipBenefitInlineFormset


class SponsorshipLevelForm(ConcurrentProtectedModelForm):
    class Meta:
        model = SponsorshipLevel
        exclude = []

    def __init__(self, *args, **kwargs):
        super(SponsorshipLevelForm, self).__init__(*args, **kwargs)
        self.fields['paymentmethods'].label_from_instance = lambda x: x.internaldescription


class SponsorshipLevelAdmin(admin.ModelAdmin):
    list_filter = ['conference', ]
    list_display = ['levelname', 'conference', ]
    inlines = [SponsorshipBenefitInline, ]
    actions = ['copy_sponsorshiplevel', ]
    form = SponsorshipLevelForm

    def copy_sponsorshiplevel(self, request, queryset):
        source_level = queryset.all()
        if len(source_level) != 1:
            raise Exception("Must copy exactly one level at a time!")

        return HttpResponseRedirect("/admin/django/confsponsor/sponsorshiplevel/{0}/copy".format(source_level[0].id))
    copy_sponsorshiplevel.short_description = "Copy sponsorship level"


class SponsorAdminForm(ConcurrentProtectedModelForm):
    def __init__(self, *args, **kwargs):
        super(SponsorAdminForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs:
            self.fields['level'].queryset = SponsorshipLevel.objects.filter(conference=self.instance.conference)
        else:
            self.fields['level'].queryset = SponsorshipLevel.objects.all().order_by('-conference__startdate', 'levelcost')
            self.fields['level'].label_from_instance = lambda x: "%s: %s" % (x.conference, x)


class SponsorClaimedBenefitInline(admin.TabularInline):
    model = SponsorClaimedBenefit
    extra = 0
    can_delete = False
    max_num = 0


class LevelListFilter(admin.SimpleListFilter):
    title = 'Level'
    parameter_name = 'level'

    def lookups(self, request, model_admin):
        cid = request.GET.get('conference__id__exact', -1)
        if cid >= 0:
            return ((l.id, l.levelname) for l in SponsorshipLevel.objects.filter(conference__id=cid))

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(level__id=self.value())


class SponsorAdmin(admin.ModelAdmin):
    exclude = ('invoice', )
    readonly_fields = ('invoice_link', )
    form = SponsorAdminForm
    inlines = [SponsorClaimedBenefitInline, ]
    list_filter = ['conference', LevelListFilter, ]
    list_display = ['name', 'level', 'conference', ]
    autocomplete_fields = ('managers', )

    def invoice_link(self, inst):
        if inst.invoice:
            url = reverse('admin:invoices_invoice_change', args=(inst.invoice.id,))
            return mark_safe('<a href="%s">%s</a>' % (url, inst.invoice))
        else:
            return ""
    invoice_link.short_description = 'Invoice'


class SponsorshipContractAdminForm(ConcurrentProtectedModelForm):
    exclude_fields_from_validation = ['contractpdf', ]

    class Meta:
        model = SponsorshipContract
        exclude = []


class SponsorshipContractAdmin(admin.ModelAdmin):
    form = SponsorshipContractAdminForm


admin.site.register(SponsorshipContract, SponsorshipContractAdmin)
admin.site.register(SponsorshipLevel, SponsorshipLevelAdmin)
admin.site.register(Sponsor, SponsorAdmin)
