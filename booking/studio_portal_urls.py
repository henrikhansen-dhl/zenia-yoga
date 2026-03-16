from django.contrib.auth import views as auth_views
from django.urls import path

from . import studio_portal_views

app_name = 'studio_portal'

urlpatterns = [
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='studio_portal/login.html',
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='studio_portal:login'),
        name='logout',
    ),
    path('', studio_portal_views.dashboard, name='dashboard'),
    path('employees/', studio_portal_views.employee_list, name='employee_list'),
    path('employees/new/', studio_portal_views.employee_create, name='employee_create'),
    path('employees/<int:pk>/edit/', studio_portal_views.employee_edit, name='employee_edit'),
    path('invoices/', studio_portal_views.invoice_list, name='invoice_list'),
    path('invoices/new/', studio_portal_views.invoice_create, name='invoice_create'),
    path('invoices/<int:pk>/', studio_portal_views.invoice_detail, name='invoice_detail'),
]