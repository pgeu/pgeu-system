class BaseProvider:
    can_send_preview = False
    has_log_details = False
    webhookcode = None

    def __init__(self, id, provider):
        self.id = id
        self.provider = provider

    def description_text(self, signeremail):
        return ''
