from functools import wraps
from django.utils.decorators import available_attrs
from django.http import HttpResponseForbidden

# This is like @user_passes_test, except if the user is logged in
# but does not pass the test we give an error instead of a new
# chance to log in. This is so we don't end up in a redirect loop
# with the community auth system.

def user_passes_test_or_error(test_func):
	def decorator(view_func):
		@wraps(view_func, assigned=available_attrs(view_func))
		def _wrapped_view(request, *args, **kwargs):
			if test_func(request.user):
				return view_func(request, *args, **kwargs)
			# Don't try to log in, just give an error
			return HttpResponseForbidden('Access denied')
		return _wrapped_view
	return decorator

