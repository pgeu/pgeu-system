class SelectableWidgetAdminFormMixin(object):
    def __init__(self, *args, **kwargs):
        super(SelectableWidgetAdminFormMixin, self).__init__(*args, **kwargs)
        for fn in self.Meta.widgets.keys():
            self.fields[fn].widget.can_add_related = False
            self.fields[fn].widget.can_change_related = False
            self.fields[fn].widget.can_delete_related = False
