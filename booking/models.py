from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class YogaClass(models.Model):
	title = models.CharField(max_length=120)
	short_description = models.CharField(max_length=180)
	description = models.TextField(blank=True)
	instructor_name = models.CharField(max_length=120)
	start_time = models.DateTimeField()
	end_time = models.DateTimeField()
	capacity = models.PositiveIntegerField(default=10)
	location = models.CharField(max_length=120, blank=True)
	focus = models.CharField(max_length=120, blank=True)
	cover_image = models.ImageField(upload_to='class-covers/', blank=True)
	is_published = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['start_time']
		verbose_name_plural = 'Yoga classes'

	def __str__(self):
		return f"{self.title} on {self.start_time:%b %d, %Y %H:%M}"

	def clean(self):
		if self.end_time and self.start_time and self.end_time <= self.start_time:
			raise ValidationError('The class end time must be after the start time.')

		if self.capacity < 1:
			raise ValidationError('Capacity must be at least 1 participant.')

	@property
	def booked_count(self):
		return self.bookings.count()

	@property
	def spots_left(self):
		return max(self.capacity - self.booked_count, 0)

	@property
	def is_past(self):
		return self.start_time <= timezone.now()

	@property
	def is_bookable(self):
		return self.is_published and not self.is_past and self.spots_left > 0


class Booking(models.Model):
	yoga_class = models.ForeignKey(
		YogaClass,
		on_delete=models.CASCADE,
		related_name='bookings',
	)
	client_name = models.CharField(max_length=120)
	client_email = models.EmailField()
	client_phone = models.CharField(max_length=40, blank=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['created_at']
		constraints = [
			models.UniqueConstraint(
				fields=['yoga_class', 'client_email'],
				name='unique_booking_email_per_class',
			)
		]

	def __str__(self):
		return f"{self.client_name} booking for {self.yoga_class.title}"

	def clean(self):
		if not self.yoga_class_id:
			return

		if self.yoga_class.start_time <= timezone.now():
			raise ValidationError('This class has already started and can no longer be booked.')

		current_bookings = self.yoga_class.bookings.exclude(pk=self.pk).count()
		if current_bookings >= self.yoga_class.capacity:
			raise ValidationError('This class is already full.')

	def save(self, *args, **kwargs):
		self.client_email = self.client_email.strip().lower()
		self.full_clean()
		super().save(*args, **kwargs)
