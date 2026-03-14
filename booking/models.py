from datetime import timedelta

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
	is_weekly_recurring = models.BooleanField(default=False)
	recurrence_parent = models.ForeignKey(
		'self',
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name='generated_occurrences',
	)
	series_participants = models.ManyToManyField(
		'Client',
		blank=True,
		related_name='weekly_series_classes',
	)
	is_published = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['start_time']
		verbose_name_plural = 'Yoga classes'
		constraints = [
			models.UniqueConstraint(
				fields=['recurrence_parent', 'start_time'],
				name='unique_recurring_occurrence_start',
			),
		]

	def __str__(self):
		return f"{self.title} on {self.start_time:%b %d, %Y %H:%M}"

	@staticmethod
	def _as_aware(value):
		if value is None:
			return None
		if timezone.is_naive(value):
			return timezone.make_aware(value, timezone.get_current_timezone())
		return value

	def clean(self):
		self.start_time = self._as_aware(self.start_time)
		self.end_time = self._as_aware(self.end_time)

		if self.recurrence_parent_id and self.is_weekly_recurring:
			raise ValidationError('Generated recurring classes cannot also be marked as weekly recurring.')

		if self.end_time and self.start_time and self.end_time <= self.start_time:
			raise ValidationError('The class end time must be after the start time.')

		if self.capacity < 1:
			raise ValidationError('Capacity must be at least 1 participant.')

		if self.recurrence_parent_id and self.recurrence_parent_id == self.pk:
			raise ValidationError('A recurring class cannot reference itself as its parent.')

	@property
	def booked_count(self):
		return self.bookings.count()

	@property
	def spots_left(self):
		return max(self.capacity - self.booked_count, 0)

	@property
	def is_past(self):
		start_time = self._as_aware(self.start_time)
		return start_time <= timezone.now()

	@property
	def is_bookable(self):
		return self.is_published and not self.is_past and self.spots_left > 0

	@property
	def recurrence_root(self):
		return self.recurrence_parent or self

	@property
	def is_generated_occurrence(self):
		return self.recurrence_parent_id is not None

	def series_queryset(self):
		root = self.recurrence_root
		return YogaClass.objects.filter(
			models.Q(pk=root.pk) | models.Q(recurrence_parent=root)
		).order_by('start_time')

	def upcoming_occurrence_starts(self, upcoming_limit=2, now=None):
		root = self.recurrence_root
		now = self._as_aware(now or timezone.now())
		root_start_time = self._as_aware(root.start_time)

		if not root.is_weekly_recurring:
			return [root_start_time] if root_start_time >= now else []

		first_upcoming = root_start_time
		if first_upcoming < now:
			weeks_to_skip = int((now - first_upcoming).total_seconds() // timedelta(days=7).total_seconds())
			first_upcoming = first_upcoming + timedelta(days=7 * weeks_to_skip)
			if first_upcoming < now:
				first_upcoming = first_upcoming + timedelta(days=7)

		return [first_upcoming + timedelta(days=7 * index) for index in range(upcoming_limit)]

	def _occurrence_defaults(self, start_time):
		duration = self.end_time - self.start_time
		return {
			'title': self.title,
			'short_description': self.short_description,
			'description': self.description,
			'instructor_name': self.instructor_name,
			'end_time': start_time + duration,
			'capacity': self.capacity,
			'location': self.location,
			'focus': self.focus,
			'cover_image': self.cover_image,
			'is_weekly_recurring': False,
			'is_published': self.is_published,
		}

	def sync_weekly_occurrences(self, upcoming_limit=2, now=None):
		root = self.recurrence_root
		now = self._as_aware(now or timezone.now())

		future_generated = root.generated_occurrences.filter(start_time__gte=now)
		if not root.is_weekly_recurring:
			future_generated.filter(bookings__isnull=True).delete()
			return

		target_starts = root.upcoming_occurrence_starts(upcoming_limit=upcoming_limit, now=now)
		root.generated_occurrences.filter(start_time__gte=now, bookings__isnull=True).exclude(
			start_time__in=target_starts,
		).delete()

		for target_start in target_starts:
			if target_start == root.start_time:
				continue

			occurrence, created = YogaClass.objects.get_or_create(
				recurrence_parent=root,
				start_time=target_start,
				defaults=root._occurrence_defaults(target_start),
			)
			if not created and not occurrence.bookings.exists():
				for field_name, value in root._occurrence_defaults(target_start).items():
					setattr(occurrence, field_name, value)
				occurrence.save()

	@classmethod
	def sync_all_weekly_occurrences(cls, upcoming_limit=2, now=None):
		now = now or timezone.now()
		for yoga_class in cls.objects.filter(is_weekly_recurring=True, recurrence_parent__isnull=True):
			yoga_class.sync_weekly_occurrences(upcoming_limit=upcoming_limit, now=now)

	def should_show_in_public_list(self, upcoming_limit=2, now=None):
		now = self._as_aware(now or timezone.now())
		start_time = self._as_aware(self.start_time)
		if start_time < now:
			return False

		root = self.recurrence_root
		if not root.is_weekly_recurring:
			return True

		return start_time in root.upcoming_occurrence_starts(upcoming_limit=upcoming_limit, now=now)

	def save(self, *args, **kwargs):
		self.start_time = self._as_aware(self.start_time)
		self.end_time = self._as_aware(self.end_time)
		self.full_clean()
		super().save(*args, **kwargs)
		if not self.recurrence_parent_id:
			self.sync_weekly_occurrences(upcoming_limit=2)


class Client(models.Model):
	name = models.CharField(max_length=120)
	email = models.EmailField(unique=True)
	phone = models.CharField(max_length=40, blank=True)
	reminder_classes = models.ManyToManyField(
		YogaClass,
		blank=True,
		related_name='reminder_clients',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['name', 'email']

	def __str__(self):
		return f"{self.name} ({self.email})"

	def clean(self):
		self.email = self.email.strip().lower()

	def save(self, *args, **kwargs):
		self.email = self.email.strip().lower()
		self.full_clean()
		super().save(*args, **kwargs)


class SmsReminderLog(models.Model):
	STATUS_SENT = 'sent'
	STATUS_FAILED = 'failed'
	STATUS_SKIPPED = 'skipped'
	STATUS_CHOICES = [
		(STATUS_SENT, 'Sent'),
		(STATUS_FAILED, 'Failed'),
		(STATUS_SKIPPED, 'Skipped'),
	]

	yoga_class = models.ForeignKey(
		YogaClass,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='sms_logs',
	)
	client_name = models.CharField(max_length=120)
	client_email = models.EmailField()
	raw_phone = models.CharField(max_length=40, blank=True)
	normalized_phone = models.CharField(max_length=40, blank=True)
	message_language = models.CharField(max_length=5, default='da')
	message_text = models.TextField()
	class_title = models.CharField(max_length=120)
	reminder_reason = models.CharField(max_length=60)
	status = models.CharField(max_length=10, choices=STATUS_CHOICES)
	gateway_reference = models.CharField(max_length=32, blank=True)
	gateway_error = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f"{self.client_name} {self.class_title} ({self.status})"


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
