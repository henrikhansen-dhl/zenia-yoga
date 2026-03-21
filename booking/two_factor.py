from urllib.parse import urlencode

from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .models import UserAuthenticatorDevice


TWO_FACTOR_SESSION_USER_KEY = 'two_factor_verified_user_id'
TWO_FACTOR_SESSION_HASH_KEY = 'two_factor_verified_auth_hash'
TWO_FACTOR_EXEMPT_PATH_PREFIXES = (
    '/two-factor/',
    '/admin/login/',
    '/admin/logout/',
    '/studio/login/',
    '/studio/logout/',
)
TWO_FACTOR_PROTECTED_PATH_PREFIXES = ('/admin/', '/studio/', '/instructor/')


def is_two_factor_protected_path(path):
    return path.startswith(TWO_FACTOR_PROTECTED_PATH_PREFIXES) and not path.startswith(TWO_FACTOR_EXEMPT_PATH_PREFIXES)


def is_two_factor_verified(request):
    if not request.user.is_authenticated:
        return False

    verified_user_id = request.session.get(TWO_FACTOR_SESSION_USER_KEY)
    verified_auth_hash = request.session.get(TWO_FACTOR_SESSION_HASH_KEY)
    return (
        verified_user_id == request.user.pk
        and verified_auth_hash == request.user.get_session_auth_hash()
    )


def mark_two_factor_verified(request):
    request.session[TWO_FACTOR_SESSION_USER_KEY] = request.user.pk
    request.session[TWO_FACTOR_SESSION_HASH_KEY] = request.user.get_session_auth_hash()


def clear_two_factor_verified(request):
    request.session.pop(TWO_FACTOR_SESSION_USER_KEY, None)
    request.session.pop(TWO_FACTOR_SESSION_HASH_KEY, None)


def get_safe_next_url(request, fallback='/studio/'):
    candidate = request.POST.get('next') or request.GET.get('next') or fallback
    if url_has_allowed_host_and_scheme(candidate, {request.get_host()}, require_https=request.is_secure()):
        return candidate
    return fallback


def build_two_factor_redirect(request, route_name):
    query = urlencode({'next': request.get_full_path()})
    return redirect(f'/two-factor/{route_name}/?{query}')


def get_user_authenticator_device(user):
    if not user.is_authenticated:
        return None
    return UserAuthenticatorDevice.objects.using('default').filter(user_id=user.pk).first()


def get_or_create_user_authenticator_device(user):
    return UserAuthenticatorDevice.objects.db_manager('default').get_or_create(user=user)