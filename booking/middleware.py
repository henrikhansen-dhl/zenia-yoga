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