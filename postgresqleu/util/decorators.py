from functools import wraps
from django.utils.decorators import available_attrs
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required


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


# Exclude an URL from global logins, if they are enabled at all
def global_login_exempt(view_func):
    def wrapped_view(*args, **kwargs):
        return view_func(*args, **kwargs)
    wrapped_view.global_login_exempt = True
    return wraps(view_func, assigned=available_attrs(view_func))(wrapped_view)


# Require superuser
def superuser_required(view_func):
    return login_required(user_passes_test_or_error(lambda u: u.is_superuser)(view_func))
