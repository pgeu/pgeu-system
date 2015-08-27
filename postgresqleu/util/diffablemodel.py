from django.forms.models import model_to_dict
import django.db.models.fields.related


class DiffableModel(object):
	"""
	Make it possible to diff a model.
    """

	def __init__(self, *args, **kwargs):
		super(DiffableModel, self).__init__(*args, **kwargs)
		self.__initial = self._dict

	@property
	def diff(self):
		manytomanyfieldnames = [f.name for f in self._meta.many_to_many]
		d1 = self.__initial
		d2 = self._dict
		diffs = dict([(k, (v, d2[k])) for k, v in d1.items() if v != d2[k]])
		# Foreign key lookups
		for k,v in diffs.items():
			if type(self._meta.get_field_by_name(k)[0]) is django.db.models.fields.related.ForeignKey:
				# If it's a foreign key, look up the name again on ourselves.
				# Since we only care about the *new* value, it's easy enough.
				diffs[k] = (v[0], getattr(self, k))
		# Many to many lookups
		if hasattr(self, 'map_manytomany_for_diff'):
			for k,v in diffs.items():
				if k in manytomanyfieldnames and self.map_manytomany_for_diff.has_key(k):
					# Try to show the display name instead here
					newvalue = getattr(self, self.map_manytomany_for_diff[k])
					diffs[k] = (v[0], newvalue)
		return diffs

	def save(self, *args, **kwargs):
		super(DiffableModel, self).save(*args, **kwargs)
		self.__initial = self._dict

	@property
	def _dict(self):
		fields = [field.name for field in self._meta.fields]
		fields.extend([field.name for field in self._meta.many_to_many])
		return model_to_dict(self, fields=fields)
