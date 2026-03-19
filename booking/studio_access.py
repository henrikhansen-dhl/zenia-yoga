from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Studio, StudioMembership
from .studio_db import activate_studio


_ROLE_ORDER = {
    StudioMembership.ROLE_STAFF: 1,
    StudioMembership.ROLE_MANAGER: 2,
    StudioMembership.ROLE_OWNER: 3,
}


def get_accessible_studios(user):
    if not user.is_authenticated:
        return Studio.objects.none()

    if user.is_superuser:
        return Studio.objects.filter(is_active=True).order_by('name')

    studios = Studio.objects.filter(
        is_active=True,
        memberships__user=user,
        memberships__is_active=True,
    ).distinct().order_by('name')
    return studios


def get_request_studio(request):
    if hasattr(request, '_cached_active_studio'):
        return request._cached_active_studio

    available_studios = get_accessible_studios(request.user)
    request.available_studios = available_studios

    if not request.user.is_authenticated:
        raise PermissionDenied('Login is required.')

    if request.user.is_superuser:
        selected_slug = request.GET.get('studio') or request.session.get('active_studio_slug')
        if selected_slug:
            selected = available_studios.filter(slug=selected_slug).first()
            if selected:
                request.session['active_studio_slug'] = selected.slug
                request._cached_active_studio = selected
                return selected

        default_studio = Studio.get_default()
        if available_studios.filter(pk=default_studio.pk).exists():
            request.session['active_studio_slug'] = default_studio.slug
            request._cached_active_studio = default_studio
            return default_studio

        selected = available_studios.first()
        if selected:
            request.session['active_studio_slug'] = selected.slug
            request._cached_active_studio = selected
            return selected

        raise PermissionDenied('No studios are available for this account.')

    selected = available_studios.first()
    if not selected:
        raise PermissionDenied('This account is not assigned to an active studio.')

    request._cached_active_studio = selected
    return selected


def studio_login_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_path = '/studio/login/' if request.path.startswith('/studio/') else '/admin/login/'
            return redirect(login_path + '?next=' + request.get_full_path())

        request.studio = get_request_studio(request)
        activate_studio(request.studio)
        if not hasattr(request, 'available_studios'):
            request.available_studios = get_accessible_studios(request.user)
        if not hasattr(request, 'studio_role'):
            request.studio_role = get_user_studio_role(request.user, request.studio)
        return view_func(request, *args, **kwargs)

    return wrapped


def superuser_portal_required(view_func):
    """Allow only superusers on /studio portal pages; redirect others to instructor area."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/studio/login/?next=' + request.get_full_path())

        if not request.user.is_superuser:
            return redirect('instructor:dashboard')

        return view_func(request, *args, **kwargs)

    return wrapped


def get_user_studio_role(user, studio):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return StudioMembership.ROLE_OWNER

    membership = StudioMembership.objects.filter(
        studio=studio,
        user=user,
        is_active=True,
    ).first()
    return membership.role if membership else None


def studio_role_required(minimum_role):
    minimum_rank = _ROLE_ORDER[minimum_role]

    def decorator(view_func):
        @studio_login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            role = get_user_studio_role(request.user, request.studio)
            if role is None or _ROLE_ORDER.get(role, 0) < minimum_rank:
                raise PermissionDenied('You do not have permission to manage this studio area.')

            request.studio_role = role
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator