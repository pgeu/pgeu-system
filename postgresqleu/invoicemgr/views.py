#!/usr/bin/env python
# -*- coding: utf-8 -*-

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse
from django.http import HttpResponseServerError
from django.contrib.auth.decorators import login_required, user_passes_test

from datetime import datetime
import os

from models import Invoice
from postgresqleu.confreg.models import Conference, ConferenceRegistration

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def home(request):
	invoices = Invoice.objects.all().order_by('id')
	return render(request, 'invoicemgr/index.html', {
		'invoices': invoices,
	})

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def invoice(request, id):
	invoice = get_object_or_404(Invoice, pk=id)
	return render(request, 'invoicemgr/viewinvoice.html', {
			'invoice': invoice,
	})

@login_required
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def invoicepdf(request, id):
	invoice = get_object_or_404(Invoice, pk=id)
	r = HttpResponse(content_type='application/pdf')
	r['Content-Disposition'] = 'attachment; filename=%s.pdf' % id
	invoice.writepdf(r)
	return r
