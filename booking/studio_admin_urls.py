from django.urls import path

from . import studio_admin_views

app_name = 'studio_admin'

urlpatterns = [
    path('', studio_admin_views.studio_list, name='index'),
    path('studios/', studio_admin_views.studio_list, name='studio_list'),
    path('studios/new/', studio_admin_views.studio_create, name='studio_create'),
    path('studios/<int:pk>/edit/', studio_admin_views.studio_edit, name='studio_edit'),
    path('features/', studio_admin_views.feature_list, name='feature_list'),
    path('features/new/', studio_admin_views.feature_create, name='feature_create'),
    path('features/<int:pk>/edit/', studio_admin_views.feature_edit, name='feature_edit'),
    path('access/', studio_admin_views.membership_list, name='membership_list'),
    path('access/new/', studio_admin_views.membership_create, name='membership_create'),
    path('access/<int:pk>/edit/', studio_admin_views.membership_edit, name='membership_edit'),
]