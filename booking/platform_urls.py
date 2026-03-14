from django.urls import path

from . import platform_views

app_name = 'platform'

urlpatterns = [
    path('', platform_views.studio_list, name='index'),
    path('studios/', platform_views.studio_list, name='studio_list'),
    path('studios/new/', platform_views.studio_create, name='studio_create'),
    path('studios/<int:pk>/edit/', platform_views.studio_edit, name='studio_edit'),
    path('features/', platform_views.feature_list, name='feature_list'),
    path('features/new/', platform_views.feature_create, name='feature_create'),
    path('features/<int:pk>/edit/', platform_views.feature_edit, name='feature_edit'),
    path('access/', platform_views.membership_list, name='membership_list'),
    path('access/new/', platform_views.membership_create, name='membership_create'),
    path('access/<int:pk>/edit/', platform_views.membership_edit, name='membership_edit'),
]