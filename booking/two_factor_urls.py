from django.urls import path

from . import two_factor_views


app_name = 'two_factor'

urlpatterns = [
    path('setup/', two_factor_views.setup, name='setup'),
    path('verify/', two_factor_views.verify, name='verify'),
]