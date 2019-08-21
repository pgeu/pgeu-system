from postgresqleu.util.backendforms import BackendForm

from postgresqleu.accounting.models import Account, AccountGroup, AccountClass, Object


class BackendAccountClassForm(BackendForm):
    helplink = 'accounting'
    list_fields = ['name', 'inbalance', ]

    class Meta:
        model = AccountClass
        fields = ['name', 'inbalance', 'balancenegative', ]


class BackendAccountGroupForm(BackendForm):
    helplink = 'accounting'
    list_fields = ['name', 'accountclass', 'foldable', ]
    queryset_select_related = ['accountclass', ]

    class Meta:
        model = AccountGroup
        fields = ['name', 'accountclass', 'foldable', ]


class BackendAccountForm(BackendForm):
    helplink = 'accounting'
    list_fields = ['num', 'name', ]

    class Meta:
        model = Account
        fields = ['num', 'name', 'group', 'availableforinvoicing', 'objectrequirement', ]


class BackendObjectForm(BackendForm):
    helplink = 'accounting'
    list_fields = ['name', 'active', ]

    class Meta:
        model = Object
        fields = ['name', 'active', ]
