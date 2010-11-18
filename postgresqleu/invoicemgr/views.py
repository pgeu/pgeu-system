from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse
from django.http import HttpResponseServerError
from django.template import RequestContext
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test

from datetime import datetime
import os

from models import Invoice
from postgresqleu.confreg.models import Conference, ConferenceRegistration

from postgresqleu.util.misc.invoice import PDFInvoice

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def home(request):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	invoices = Invoice.objects.all().order_by('id')
	return render_to_response('invoicemgr/index.html', {
		'invoices': invoices,
	}, context_instance=RequestContext(request))

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def invoice(request, id):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	invoice = get_object_or_404(Invoice, pk=id)
	return render_to_response('invoicemgr/viewinvoice.html', {
			'invoice': invoice,
	})

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def invoicepdf(request, id):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	invoice = get_object_or_404(Invoice, pk=id)
	r = HttpResponse(mimetype='application/pdf')
	r['Content-Disposition'] = 'attachment; filename=%s.pdf' % id
	invoice.writepdf(r)
	return r

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def conf(request, confid=None):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	if confid:
		confid = int(confid.replace('/',''))
		conference = get_object_or_404(Conference, pk=confid)
		attendees = conference.conferenceregistration_set.all()
	else:
		conference = None
		attendees = None

	if request.method == 'POST':
		# Handle the form, generate the invoice
		if len(request.POST['recipient']) < 3:
			return HttpResponseServerError("You must specify an invoice recipient!")
		if len(request.POST['duedate']) != 10:
			return HttpResponseServerError("You must specify a due date in the format yyyy-mm-dd")
		duedate = datetime.strptime(request.POST['duedate'], "%Y-%m-%d")

		# Add all attendees
		attendeeids = []
		for k,v in request.POST.items():
			if k.startswith("att") and v=='1' :
				attendeeids.append(int(k[3:]))
		attendees = ConferenceRegistration.objects.filter(id__in=attendeeids)

		dbinvoice = Invoice(invoicedate = datetime.today(),
							recipient = request.POST['recipient'],
							duedate = duedate)
		dbinvoice.save() # generate primary key
		invoice = PDFInvoice(dbinvoice.recipient,
							 datetime.today(),
							 duedate,
							 dbinvoice.id,
							 os.path.realpath('%s/../../media/img/' % os.path.dirname(__file__)))

		for a in attendees:
			# Add the base registration fee (if applicable)
			attendeecost = 0

			if a.regtype.cost > 0 or len(a.additionaloptions.all()) > 0:
				# If there are additional options, add a 0 cost row for the
				# registration itself, so it groups properly.
				invoice.addrow("%s - %s (%s)" % (a.conference, a.regtype.regtype, a.email), a.regtype.cost)
				attendeecost += a.regtype.cost

			for o in a.additionaloptions.all():
				# Add any additional options (training etc), if any
				if o.cost > 0:
					invoice.addrow("   %s" % o.name, o.cost)
					attendeecost += o.cost

			# If this is confirmed, zero out the cost, making it a receipt
			if a.payconfirmedat:
				invoice.addrow("   Payment received %s" % a.payconfirmedat, -attendeecost)
			else:
				dbinvoice.totalamount += attendeecost

		# Store PDF in the db
		dbinvoice.setpdf(invoice.save())

		# Let's hope we can save...
		dbinvoice.save()

		return HttpResponseRedirect("/invoicemgr/%s/" % dbinvoice.id)

	# Create the form
	conferences = Conference.objects.all()
	invoices = Invoice.objects.all().order_by('id')
	return render_to_response('invoicemgr/conference.html', {
		'conference': conference,
		'conferences': conferences,
		'attendees': attendees,
	}, context_instance=RequestContext(request))
