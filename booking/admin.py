from django.contrib import admin

from .models import Booking, YogaClass


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
		'capacity',
		'booked_count',
		'spots_left',
		'is_published',
	)
	list_filter = ('is_published', 'instructor_name', 'start_time')
	search_fields = ('title', 'instructor_name', 'location', 'focus')
	inlines = [BookingInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
	list_display = ('client_name', 'client_email', 'yoga_class', 'created_at')
	search_fields = ('client_name', 'client_email', 'yoga_class__title')
	list_select_related = ('yoga_class',)
