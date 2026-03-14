from django.contrib import admin

from .models import Booking, Client, Feature, SmsReminderLog, Studio, StudioFeatureAccess, StudioMembership, YogaClass


class BookingInline(admin.TabularInline):
	model = Booking
	extra = 0
	fields = ('studio', 'client_name', 'client_email', 'client_phone', 'created_at')
	readonly_fields = ('created_at',)
	raw_id_fields = ('studio',)


class StudioFeatureAccessInline(admin.TabularInline):
	model = StudioFeatureAccess
	extra = 0


class StudioMembershipInline(admin.TabularInline):
	model = StudioMembership
	extra = 0
	raw_id_fields = ('user',)


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
	list_display = ('name', 'slug', 'contact_email', 'billing_email', 'is_active', 'created_at')
	list_filter = ('is_active',)
	search_fields = ('name', 'slug', 'contact_name', 'contact_email', 'billing_email')
	prepopulated_fields = {'slug': ('name',)}
	inlines = [StudioFeatureAccessInline, StudioMembershipInline]


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
	list_display = ('name', 'code', 'is_active', 'created_at')
	list_filter = ('is_active',)
	search_fields = ('name', 'code', 'description')


@admin.register(StudioMembership)
class StudioMembershipAdmin(admin.ModelAdmin):
	list_display = ('studio', 'user', 'role', 'is_active', 'created_at')
	list_filter = ('studio', 'role', 'is_active', 'created_at')
	search_fields = ('studio__name', 'user__username', 'user__email', 'user__first_name', 'user__last_name')
	raw_id_fields = ('user',)


@admin.register(YogaClass)
class YogaClassAdmin(admin.ModelAdmin):
	list_display = (
		'studio',
		'title',
		'instructor_name',
		'start_time',
		'is_weekly_recurring',
		'capacity',
		'booked_count',
		'spots_left',
		'is_published',
	)
	list_filter = ('studio', 'is_published', 'is_weekly_recurring', 'instructor_name', 'start_time')
	search_fields = ('title', 'instructor_name', 'location', 'focus')
	readonly_fields = ('recurrence_parent',)
	inlines = [BookingInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
	list_display = ('studio', 'client_name', 'client_email', 'yoga_class', 'created_at')
	search_fields = ('client_name', 'client_email', 'yoga_class__title')
	list_filter = ('studio', 'created_at')
	list_select_related = ('yoga_class',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
	list_display = ('studio', 'name', 'email', 'phone', 'created_at')
	search_fields = ('name', 'email', 'phone')
	list_filter = ('studio', 'created_at')
	filter_horizontal = ('reminder_classes',)


@admin.register(SmsReminderLog)
class SmsReminderLogAdmin(admin.ModelAdmin):
	list_display = (
		'studio',
		'created_at',
		'client_name',
		'client_email',
		'normalized_phone',
		'class_title',
		'reminder_reason',
		'status',
	)
	list_filter = ('studio', 'status', 'message_language', 'reminder_reason', 'created_at')
	search_fields = ('client_name', 'client_email', 'normalized_phone', 'class_title', 'gateway_reference', 'gateway_error')
	list_select_related = ('yoga_class',)
	readonly_fields = ('created_at',)
