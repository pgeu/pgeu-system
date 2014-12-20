class BaseBenefit(object):
	default_params = ''
	def __init__(self, level, params):
		self.level = level
		self.params = params

	def validate_params(self):
		pass

	def render_claimdata(self, claimedbenefit):
		return ''

	def save_form(self, form, claim, request):
		raise Exception("Form saving not implemented!")
