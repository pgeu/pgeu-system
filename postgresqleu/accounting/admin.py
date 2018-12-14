from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from models import AccountClass, AccountGroup, Account, IncomingBalance
from models import JournalEntry, JournalItem, JournalUrl, Object, Year


class AccountClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'inbalance', 'balancenegative')


class AccountAdmin(admin.ModelAdmin):
    list_display = ('num', 'name')


class JournalItemFormset(BaseInlineFormSet):
    def clean(self):
        super(JournalItemFormset, self).clean()
        if len(self.forms) == 0:
            raise ValidationError("Cannot save with no entries")
        s = sum([f.cleaned_data['amount'] for f in self.forms if hasattr(f, 'cleaned_data') and f.cleaned_data and not f.cleaned_data.get('DELETE', False)])
        if s != 0:
            raise ValidationError("Journal entry does not balance!")


class JournalItemInline(admin.TabularInline):
    model = JournalItem
    formset = JournalItemFormset


class JournalUrlInline(admin.TabularInline):
    model = JournalUrl


class JournalEntryAdmin(admin.ModelAdmin):
    inlines = [JournalItemInline, JournalUrlInline]
    list_display = ('__unicode__', 'year', 'seq', 'date', 'closed')


class IncomingBalanceAdmin(admin.ModelAdmin):
    list_display = ('__unicode__', 'year', 'account', 'amount')


class ObjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'active')


class YearAdmin(admin.ModelAdmin):
    readonly_fields = ('year',)


admin.site.register(AccountClass, AccountClassAdmin)
admin.site.register(AccountGroup)
admin.site.register(Account, AccountAdmin)
admin.site.register(IncomingBalance, IncomingBalanceAdmin)
admin.site.register(JournalEntry, JournalEntryAdmin)
admin.site.register(Object, ObjectAdmin)
admin.site.register(Year, YearAdmin)
