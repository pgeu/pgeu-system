# The PaymentMethodWrapper needs to be in it's own class, so we don't
# create a circular dependency between models and util.

class PaymentMethodWrapper(object):
	def __init__(self, method, invoicestr, invoiceamount, invoiceid, returnurl=None):
		self.method = method
		self.invoicestr = invoicestr
		self.invoiceamount = invoiceamount
		self.invoiceid = invoiceid
		self.returnurl = returnurl

		try:
			pieces = method.classname.split('.')
			modname = '.'.join(pieces[:-1])
			classname = pieces[-1]
			mod = __import__(modname, fromlist=[classname, ])
			self.implementation = getattr(mod, classname) ()
			self.ok = True
		except Exception, ex:
			print ex
			self.ok = False

	@property
	def name(self):
		return self.method.name

	@property
	def description(self):
		return self.implementation.description

	@property
	def paymenturl(self):
		try:
			return self.implementation.build_payment_url(self.invoicestr, self.invoiceamount, self.invoiceid, self.returnurl)
		except Exception, ex:
			print ex

