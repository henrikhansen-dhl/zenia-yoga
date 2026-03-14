from django.conf import settings
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Studio(models.Model):
	name = models.CharField(max_length=140)
	slug = models.SlugField(max_length=160, unique=True)
	contact_name = models.CharField(max_length=120, blank=True)
	contact_email = models.EmailField(blank=True)
	contact_phone = models.CharField(max_length=40, blank=True)
	billing_email = models.EmailField(blank=True)
	subscription_notes = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name

	@property
	def enabled_feature_accesses(self):
		return self.feature_accesses.filter(is_enabled=True).select_related('feature').order_by('feature__name')

	@property
	def enabled_feature_codes(self):
		return list(self.enabled_feature_accesses.values_list('feature__code', flat=True))

	@property
	def active_memberships(self):
		return self.memberships.filter(is_active=True).select_related('user').order_by('user__username')

	@classmethod
	def get_default(cls):
		studio, _ = cls.objects.get_or_create(
			slug='zenia-yoga',
			defaults={
				'name': 'Zenia Yoga',
				'is_active': True,
			},
		)
		return studio


class Feature(models.Model):
	code = models.SlugField(max_length=80, unique=True)
	name = models.CharField(max_length=120)
	description = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name


class StudioFeatureAccess(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.CASCADE,
		related_name='feature_accesses',
	)
	feature = models.ForeignKey(
		Feature,
		on_delete=models.CASCADE,
		related_name='studio_accesses',
	)
	is_enabled = models.BooleanField(default=True)
	enabled_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['studio__name', 'feature__name']
		constraints = [
			models.UniqueConstraint(
				fields=['studio', 'feature'],
				name='unique_feature_access_per_studio',
			),
		]

	def __str__(self):
		state = 'enabled' if self.is_enabled else 'disabled'
		return f'{self.studio.name} - {self.feature.name} ({state})'


class StudioMembership(models.Model):
	ROLE_OWNER = 'owner'
	ROLE_MANAGER = 'manager'
	ROLE_STAFF = 'staff'
	ROLE_CHOICES = [
		(ROLE_OWNER, 'Owner'),
		(ROLE_MANAGER, 'Manager'),
		(ROLE_STAFF, 'Staff'),
	]

	studio = models.ForeignKey(
		Studio,
		on_delete=models.CASCADE,
		related_name='memberships',
	)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='studio_memberships',
	)
	role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MANAGER)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['studio__name', 'user__username']
		constraints = [
			models.UniqueConstraint(
				fields=['studio', 'user'],
				name='unique_studio_membership_per_user',
			),
		]

	def __str__(self):
		return f'{self.user} - {self.studio.name} ({self.role})'


class YogaClass(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='classes',
	)
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

		if self.recurrence_parent_id and self.recurrence_parent and self.recurrence_parent.studio_id != self.studio_id:
			raise ValidationError('Recurring classes must belong to the same studio as the parent series.')

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
			'studio': self.studio,
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
		if not self.studio_id:
			self.studio = Studio.get_default()
		self.start_time = self._as_aware(self.start_time)
		self.end_time = self._as_aware(self.end_time)
		self.full_clean()
		super().save(*args, **kwargs)
		if not self.recurrence_parent_id:
			self.sync_weekly_occurrences(upcoming_limit=2)


class Client(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='clients',
	)
	name = models.CharField(max_length=120)
	email = models.EmailField()
	phone = models.CharField(max_length=40, blank=True)
	reminder_classes = models.ManyToManyField(
		YogaClass,
		blank=True,
		related_name='reminder_clients',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['name', 'email']
		constraints = [
			models.UniqueConstraint(
				fields=['studio', 'email'],
				name='unique_client_email_per_studio',
			),
		]

	def __str__(self):
		return f"{self.name} ({self.email})"

	def clean(self):
		self.email = self.email.strip().lower()

	def save(self, *args, **kwargs):
		if not self.studio_id:
			self.studio = Studio.get_default()
		self.email = self.email.strip().lower()
		self.full_clean()
		super().save(*args, **kwargs)


class SmsReminderLog(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='sms_logs',
	)
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

	def save(self, *args, **kwargs):
		if not self.studio_id:
			if self.yoga_class_id:
				self.studio_id = self.yoga_class.studio_id
			else:
				self.studio = Studio.get_default()
		super().save(*args, **kwargs)


class Booking(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='bookings',
	)
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

		if not self.studio_id:
			self.studio_id = self.yoga_class.studio_id

		if self.studio_id != self.yoga_class.studio_id:
			raise ValidationError('Bookings must belong to the same studio as the selected class.')

		if self.yoga_class.start_time <= timezone.now():
			raise ValidationError('This class has already started and can no longer be booked.')

		current_bookings = self.yoga_class.bookings.exclude(pk=self.pk).count()
		if current_bookings >= self.yoga_class.capacity:
			raise ValidationError('This class is already full.')

	def save(self, *args, **kwargs):
		if not self.studio_id and self.yoga_class_id:
			self.studio_id = self.yoga_class.studio_id
		elif not self.studio_id:
			self.studio = Studio.get_default()
		self.client_email = self.client_email.strip().lower()
		self.full_clean()
		super().save(*args, **kwargs)
