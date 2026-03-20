"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from booking import studio_admin_views

admin.site.site_header = 'Yoga Studio Admin'
admin.site.site_title = 'Yoga Studio Admin'
admin.site.index_title = 'Studio administration'

urlpatterns = [
    path('two-factor/', include('booking.two_factor_urls')),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    re_path(r'^studios/?$', studio_admin_views.legacy_studios_root_redirect),
    re_path(r'^platform/(?P<subpath>.*)$', studio_admin_views.legacy_studio_admin_redirect),
    path('studio/', include('booking.studio_portal_urls')),
    path('studio/', include('booking.studio_admin_urls')),
    path('instructor/', include('booking.instructor_urls')),
    path('', include('booking.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
