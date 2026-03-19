from django.urls import path

from booking import instructor_views

app_name = 'instructor'

urlpatterns = [
    path('', instructor_views.dashboard, name='dashboard'),
    path('classes/', instructor_views.class_list, name='class_list'),
    path('clients/', instructor_views.client_list, name='client_list'),
    path('clients/<int:pk>/edit/', instructor_views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', instructor_views.client_delete, name='client_delete'),
    path('clients/reminders/export/', instructor_views.export_sms_reminders, name='export_sms_reminders'),
    path('clients/reminders/send/', instructor_views.send_sms_reminders, name='send_sms_reminders'),
    path('classes/new/', instructor_views.class_create, name='class_create'),
    path('classes/<int:pk>/', instructor_views.class_detail, name='class_detail'),
    path('classes/<int:pk>/edit/', instructor_views.class_edit, name='class_edit'),
    path('classes/<int:pk>/participants/', instructor_views.class_participants_update, name='class_participants_update'),
    path('classes/<int:pk>/participants/add/', instructor_views.class_participant_quick_add, name='class_participant_quick_add'),
    path('classes/<int:pk>/participants/<int:client_pk>/remove/', instructor_views.class_participant_remove, name='class_participant_remove'),
    path('classes/<int:pk>/bookings/add/', instructor_views.class_booking_add, name='class_booking_add'),
    path('classes/<int:pk>/toggle-publish/', instructor_views.class_toggle_publish, name='class_toggle_publish'),
    path('classes/<int:pk>/delete/', instructor_views.class_delete, name='class_delete'),
    path('bookings/<int:pk>/delete/', instructor_views.booking_delete, name='booking_delete'),
]
