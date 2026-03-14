from django.urls import path

from . import instructor_views, views

app_name = 'booking'

urlpatterns = [
    path('', views.class_list, name='class_list'),
    path('classes/<int:pk>/', views.class_detail, name='class_detail'),
]

# Instructor namespace is included via config/urls.py