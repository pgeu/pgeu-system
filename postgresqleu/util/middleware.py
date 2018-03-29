from django import http
from django import shortcuts
from django.conf import settings

import base64

class FilterPersistMiddleware(object):
	def process_request(self, request):

		path = request.path
		if path.find('/admin/') != -1: #Dont waste time if we are not in admin
			query_string = request.META['QUERY_STRING']
			if not request.META.has_key('HTTP_REFERER'):
				return None

			session = request.session
			if session.get('redirected', False):#so that we dont loop once redirected
				del session['redirected']
				return None

			referrer = request.META['HTTP_REFERER'].split('?')[0]
			referrer = referrer[referrer.find('/admin'):len(referrer)]
			key = 'key'+path.replace('/','_')

			if path == referrer: #We are in same page as before
				if query_string == '': #Filter is empty, delete it
					if session.get(key,False):
						del session[key]
					return None
				request.session[key] = query_string
			elif '_directlink=1' in query_string: # Direct link to a filter, by ourselves, so remove it
				redirect_to = path+'?'+query_string.replace('&_directlink=1','')
				if session.has_key(key):
					del session[key]
				return http.HttpResponseRedirect(redirect_to)
			else: #We are are coming from another page, restore filter if available
				if session.get(key, False):
					query_string=request.session.get(key)
					redirect_to = path+'?'+query_string
					request.session['redirected'] = True
					return http.HttpResponseRedirect(redirect_to)
				else:
					return None
		else:
			return None



class GlobalLoginMiddleware(object):
	def process_view(self, request, callback, callback_args, callback_kwargs):
		if not settings.GLOBAL_LOGIN_USER or not settings.GLOBAL_LOGIN_PASSWORD:
			# Not configured to do global auth
			return None

		if getattr(callback, 'global_login_exempt', False):
			# No global auth on this specific url
			return None

		if 'HTTP_AUTHORIZATION' in request.META:
			auth = request.META['HTTP_AUTHORIZATION'].split()
			if len(auth) != 2:
				return http.HttpResponseForbidden("Invalid authentication")
			if auth[0].lower() == "basic":
				user, pwd = base64.b64decode(auth[1]).split(':')
				if user == settings.GLOBAL_LOGIN_USER and pwd == settings.GLOBAL_LOGIN_PASSWORD:
					return None
			# Else we fall through and request a login prompt

		response = http.HttpResponse()
		response.status_code = 401
		response['WWW-Authenticate'] = 'Basic realm={0}'.format(settings.SITEBASE)
		return response

# Ability to redirect using raise()
class RedirectException(Exception):
	def __init__(self, url):
		self.url = url

class RedirectMiddleware(object):
	def process_exception(self, request, exception):
		if isinstance(exception, RedirectException):
			return shortcuts.redirect(exception.url)
