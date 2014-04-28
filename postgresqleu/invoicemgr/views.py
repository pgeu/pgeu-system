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
