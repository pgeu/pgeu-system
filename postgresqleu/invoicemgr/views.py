#!/usr/bin/env python
# -*- coding: utf-8 -*-

from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse
from django.http import HttpResponseServerError
from django.template import RequestContext
from django.contrib.auth.decorators import login_required, user_passes_test

from datetime import datetime
import os

from models import Invoice
from postgresqleu.util.decorators import ssl_required
from postgresqleu.confreg.models import Conference, ConferenceRegistration

from postgresqleu.util.misc.invoice import PDFInvoice

@ssl_required
@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def home(request):
	invoices = Invoice.objects.all().order_by('id')
	return render_to_response('invoicemgr/index.html', {
		'invoices': invoices,
	}, context_instance=RequestContext(request))

@ssl_required
@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def invoice(request, id):
	invoice = get_object_or_404(Invoice, pk=id)
	return render_to_response('invoicemgr/viewinvoice.html', {
			'invoice': invoice,
	})

@ssl_required
@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def invoicepdf(request, id):
	invoice = get_object_or_404(Invoice, pk=id)
	r = HttpResponse(mimetype='application/pdf')
	r['Content-Disposition'] = 'attachment; filename=%s.pdf' % id
	invoice.writepdf(r)
	return r


@ssl_required
@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def create(request):
	if request.method == 'POST':
		# Handle the form, generate the invoice

		if len(request.POST['recipient']) < 3:
			return HttpResponseServerError("You must specify an invoice recipient!")
		if len(request.POST['duedate']) != 10:
			return HttpResponseServerError("You must specify a due date in the format yyyy-mm-dd")
		duedate = datetime.strptime(request.POST['duedate'], "%Y-%m-%d")
		currency = request.POST['currency']
		if len(currency) < 1:
			return HttpResponseServerError("You must specify a currency, either single character (€, $) or abbreviation (SEK, DKK)")


		rows = []
		for i in range(0,10):
			if request.POST['text_%s' % i]:
				# This row exists, validate contents
				if not request.POST['count_%s' % i]:
					return HttpResponseServerError("Invoice item '%s' is missing a count" % request.POST['text_%s' % i])
				if not request.POST['price_%s' % i]:
					return HttpResponseServerError("Invoice item '%s' is missing a price" % request.POST['text_%s' % i])
				if not request.POST['count_%s' % i].isdigit():
					return HttpResponseServerError("Invoice item '%s' has a non-numeric count" % request.POST['text_%s' % i])
				try:
					float(request.POST['price_%s' % i])
				except ValueError:
					return HttpResponseServerError("Invoice item '%s' has a non-numeric price" % request.POST['text_%s' % i])
				rows.append((request.POST['text_%s' % i],
							 int(request.POST['count_%s' % i]),
							 float(request.POST['price_%s' % i])))
			else:
				# First blank row, stop processing here
				break

		if not len(rows) > 0:
			return HttpResponseServerError("No invoice rows found")

		# Turn our data into an invoice
		dbinvoice = Invoice(invoicedate = datetime.today(),
							recipient = request.POST['recipient'],
							duedate = duedate,
							currency = currency)
		dbinvoice.save() # generate primary key
		invoice = PDFInvoice(dbinvoice.recipient,
							 datetime.today(),
							 duedate,
							 dbinvoice.id,
							 os.path.realpath('%s/../../media/img/' % os.path.dirname(__file__)),
							 currency)

		for r in rows:
			invoice.addrow(r[0],r[2],r[1])
		dbinvoice.totalamount = sum([r[1]*r[2] for r in rows])

		# Store PDF in the db
		dbinvoice.setpdf(invoice.save())

		# Let's hope we can save...
		dbinvoice.save()
		return HttpResponseRedirect("/invoicemgr/%s/" % dbinvoice.id)

	# Create the form
	return render_to_response('invoicemgr/create.html', {
			'n': range(0,10),
	}, context_instance=RequestContext(request))



@ssl_required
@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def conf(request, confid=None):
	if confid:
		confid = int(confid.replace('/',''))
		conference = get_object_or_404(Conference, pk=confid)
		attendees = conference.conferenceregistration_set.all()
	else:
		conference = None
		attendees = None

	if request.method == 'POST':
		# Handle the form, generate the invoice

		# Add all attendees
		attendeeids = []
		for k,v in request.POST.items():
			if k.startswith("att") and v=='1' :
				attendeeids.append(int(k[3:]))
		attendees = ConferenceRegistration.objects.filter(id__in=attendeeids)
		if len(attendees) < 1:
			return HttpResponseServerError("You must select at least one attendee!")

		# Check or generate the recipient address
		if request.POST.has_key('copyaddr') and request.POST['copyaddr'] == '1':
			# Copy the address from the first entry. This requires that there is only one entry
			if len(attendees) != 1:
				return HttpResponseServerError("When copying address, only one attendee can be selected!")
			recipient = "%s %s\n%s\n%s\n%s" % (
				attendees[0].firstname,
				attendees[0].lastname,
				attendees[0].company,
				attendees[0].address,
				attendees[0].country,
				)
		else:
			if len(request.POST['recipient']) < 3:
				return HttpResponseServerError("You must specify an invoice recipient!")
			recipient = request.POST['recipient']

		# Verify the due date
		if len(request.POST['duedate']) != 10:
			return HttpResponseServerError("You must specify a due date in the format yyyy-mm-dd")
		duedate = datetime.strptime(request.POST['duedate'], "%Y-%m-%d")

		# Now build the actual invoice
		dbinvoice = Invoice(invoicedate = datetime.today(),
							recipient = recipient,
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
