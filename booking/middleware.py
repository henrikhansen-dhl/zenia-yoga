from django.conf import settings


class DefaultLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        has_cookie_language = settings.LANGUAGE_COOKIE_NAME in request.COOKIES

        if not has_cookie_language:
            request.COOKIES = request.COOKIES.copy()
            request.COOKIES[settings.LANGUAGE_COOKIE_NAME] = settings.LANGUAGE_CODE

        return self.get_response(request)


class StudioContextMiddleware:
    """
    Clears the per-thread studio database context at the start (and end) of
    every request so that a previous request's studio context never leaks
    into the next request handled by the same WSGI thread.

    Must be placed *before* any middleware or view that performs studio-
    aware database queries.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .studio_db import deactivate_studio
        deactivate_studio()
        try:
            return self.get_response(request)
        finally:
            deactivate_studio()