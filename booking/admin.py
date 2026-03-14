from django.contrib import admin

from .models import Booking, Client, SmsReminderLog, YogaClass


class BookingInline(admin.TabularInline):
	model = Booking
	extra = 0
	fields = ('client_name', 'client_email', 'client_phone', 'created_at')
	readonly_fields = ('created_at',)


@admin.register(YogaClass)
class YogaClassAdmin(admin.ModelAdmin):
	list_display = (
		'title',
		'instructor_name',
		'start_time',
		'is_weekly_recurring',
		'capacity',
		'booked_count',
		'spots_left',
		'is_published',
	)
	list_filter = ('is_published', 'is_weekly_recurring', 'instructor_name', 'start_time')
	search_fields = ('title', 'instructor_name', 'location', 'focus')
	readonly_fields = ('recurrence_parent',)
	inlines = [BookingInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
	list_display = ('client_name', 'client_email', 'yoga_class', 'created_at')
	search_fields = ('client_name', 'client_email', 'yoga_class__title')
	list_select_related = ('yoga_class',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
	list_display = ('name', 'email', 'phone', 'created_at')
	search_fields = ('name', 'email', 'phone')
	filter_horizontal = ('reminder_classes',)


@admin.register(SmsReminderLog)
class SmsReminderLogAdmin(admin.ModelAdmin):
	list_display = (
		'created_at',
		'client_name',
		'client_email',
		'normalized_phone',
		'class_title',
		'reminder_reason',
		'status',
	)
	list_filter = ('status', 'message_language', 'reminder_reason', 'created_at')
	search_fields = ('client_name', 'client_email', 'normalized_phone', 'class_title', 'gateway_reference', 'gateway_error')
	list_select_related = ('yoga_class',)
	readonly_fields = ('created_at',)
