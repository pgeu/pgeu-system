from datetime import datetime, date
from decimal import Decimal
import json


class JsonSerializer(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime) or isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if hasattr(obj, 'json_included_attributes'):
            return dict([(k, getattr(obj, k)) for k in obj.json_included_attributes])
        return json.JSONEncoder.default(self, obj)
