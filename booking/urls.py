from django.urls import path

from . import instructor_views, views

app_name = 'booking'

urlpatterns = [
    path('', views.default_class_list_redirect, name='public_home'),
    path('classes/<int:pk>/', views.legacy_class_detail_redirect, name='legacy_class_detail'),
    path('studios/<slug:studio_slug>/', views.class_list, name='class_list'),
    path('studios/<slug:studio_slug>/classes/<int:pk>/', views.class_detail, name='class_detail'),
]

# Instructor namespace is included via config/urls.py