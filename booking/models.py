from django.conf import settings
from datetime import timedelta
import base64
import hashlib
import hmac
import time

from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

import pyotp


class Studio(models.Model):
	name = models.CharField(max_length=140)
	slug = models.SlugField(max_length=160, unique=True)
	logo = models.ImageField(upload_to='studio-logos/', blank=True)
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

	@property
	def can_manage_team(self):
		return self.role in {self.ROLE_OWNER, self.ROLE_MANAGER}


class UserAuthenticatorDevice(models.Model):
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='authenticator_device',
	)
	secret_encrypted = models.TextField(blank=True)
	is_confirmed = models.BooleanField(default=False)
	confirmed_at = models.DateTimeField(null=True, blank=True)
	last_verified_step = models.BigIntegerField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['user__username']
		verbose_name = 'authenticator device'
		verbose_name_plural = 'authenticator devices'

	def __str__(self):
		state = 'confirmed' if self.is_confirmed else 'pending'
		return f'{self.user} authenticator ({state})'

	@staticmethod
	def _cipher():
		key_material = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
		return Fernet(base64.urlsafe_b64encode(key_material))

	@property
	def has_secret(self):
		return bool(self.secret_encrypted)

	@property
	def secret(self):
		if not self.secret_encrypted:
			return ''
		return self._cipher().decrypt(self.secret_encrypted.encode('utf-8')).decode('utf-8')

	def set_secret(self, secret, *, confirmed=False):
		self.secret_encrypted = self._cipher().encrypt(secret.encode('utf-8')).decode('utf-8')
		self.is_confirmed = confirmed
		self.confirmed_at = timezone.now() if confirmed else None
		self.last_verified_step = None

	def regenerate_secret(self):
		self.set_secret(pyotp.random_base32(), confirmed=False)

	def ensure_secret(self):
		if not self.has_secret:
			self.regenerate_secret()
		return self.secret

	def provisioning_uri(self):
		secret = self.ensure_secret()
		account_name = self.user.email or self.user.get_username()
		return pyotp.TOTP(secret).provisioning_uri(
			name=account_name,
			issuer_name='Yoga Studio Admin',
		)

	def _matching_step(self, token, valid_window=1):
		normalized_token = ''.join(character for character in str(token or '') if character.isdigit())
		if len(normalized_token) != 6 or not self.has_secret:
			return None

		totp = pyotp.TOTP(self.secret)
		current_step = int(time.time() // totp.interval)
		for offset in range(-valid_window, valid_window + 1):
			candidate_step = current_step + offset
			candidate_code = totp.at(candidate_step * totp.interval)
			if hmac.compare_digest(candidate_code, normalized_token):
				return candidate_step
		return None

	def verify_token(self, token, *, valid_window=1, confirm=True):
		matching_step = self._matching_step(token, valid_window=valid_window)
		if matching_step is None:
			return False

		if self.last_verified_step is not None and matching_step <= self.last_verified_step:
			return False

		self.last_verified_step = matching_step
		if confirm and not self.is_confirmed:
			self.is_confirmed = True
			self.confirmed_at = timezone.now()
		self.save(update_fields=['last_verified_step', 'is_confirmed', 'confirmed_at', 'updated_at'])
		return True


class StudioInvoice(models.Model):
	STATUS_DRAFT = 'draft'
	STATUS_ISSUED = 'issued'
	STATUS_PAID = 'paid'
	STATUS_CHOICES = [
		(STATUS_DRAFT, 'Draft'),
		(STATUS_ISSUED, 'Issued'),
		(STATUS_PAID, 'Paid'),
	]

	studio = models.ForeignKey(
		Studio,
		on_delete=models.CASCADE,
		related_name='invoices',
	)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='created_studio_invoices',
	)
	invoice_number = models.CharField(max_length=40, unique=True)
	period_start = models.DateField()
	period_end = models.DateField()
	currency = models.CharField(max_length=8, default='DKK')
	status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
	notes = models.TextField(blank=True)
	issued_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f'{self.invoice_number} - {self.studio.name}'

	@property
	def subtotal_amount(self):
		return sum((line.line_total for line in self.lines.all()), start=0)


class StudioInvoiceLine(models.Model):
	invoice = models.ForeignKey(
		StudioInvoice,
		on_delete=models.CASCADE,
		related_name='lines',
	)
	description = models.CharField(max_length=255)
	quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
	unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	sort_order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ['sort_order', 'id']

	def __str__(self):
		return f'{self.invoice.invoice_number} - {self.description}'

	@property
	def line_total(self):
		return self.quantity * self.unit_price


class YogaClass(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='classes',
		db_constraint=False,
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
	series_prebooked_participants = models.ManyToManyField(
		'Client',
		blank=True,
		related_name='weekly_prebooked_series_classes',
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
		return self.bookings.count() + self.prebooked_reservation_count()

	@property
	def spots_left(self):
		return max(self.capacity - self.booked_count, 0)

	def prebooked_reservation_count(self, exclude_phone=None):
		return len(self.prebooked_reservation_clients_without_booking(exclude_phone=exclude_phone))

	def prebooked_reservation_clients_without_booking(self, exclude_phone=None):
		if self.is_past:
			return []

		root = self.recurrence_root
		if not root.is_weekly_recurring:
			return []

		excluded_phone = (exclude_phone or '').strip()
		opted_out_ids = set(self.series_prebooking_opt_outs.values_list('client_id', flat=True))
		booked_phone_keys = {
			(booking.client_phone or '').strip()
			for booking in self.bookings.all()
			if booking.client_phone
		}

		reserved_clients = []
		for participant in root.series_prebooked_participants.all():
			if participant.pk in opted_out_ids:
				continue

			participant_phone = (participant.phone or '').strip()
			if excluded_phone and participant_phone and participant_phone == excluded_phone:
				continue

			if participant_phone and participant_phone in booked_phone_keys:
				continue

			reserved_clients.append(participant)

		return reserved_clients

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
			yoga_class.sync_series_prebookings(upcoming_limit=upcoming_limit, now=now)

	def should_show_in_public_list(self, upcoming_limit=2, now=None):
		now = self._as_aware(now or timezone.now())
		start_time = self._as_aware(self.start_time)
		if start_time < now:
			return False

		root = self.recurrence_root
		if not root.is_weekly_recurring:
			return True

		return start_time in root.upcoming_occurrence_starts(upcoming_limit=upcoming_limit, now=now)

	def prebooked_participant_by_phone(self, phone):
		normalized_phone = (phone or '').strip()
		if not normalized_phone:
			return None
		return self.recurrence_root.series_prebooked_participants.filter(phone=normalized_phone).first()

	def mark_prebooked_client_opted_out(self, client):
		if not client or not self.recurrence_root.series_prebooked_participants.filter(pk=client.pk).exists():
			return
		SeriesPrebookingOptOut.objects.get_or_create(
			studio=self.studio,
			yoga_class=self,
			client=client,
		)

	def clear_prebooked_client_opt_out(self, client):
		if not client:
			return
		self.series_prebooking_opt_outs.filter(client=client).delete()

	def sync_series_prebookings(self, upcoming_limit=2, now=None):
		root = self.recurrence_root
		if not root.is_weekly_recurring:
			return

		now = self._as_aware(now or timezone.now())
		participants = {
			participant.phone.strip(): participant
			for participant in root.series_prebooked_participants.all().order_by('name')
			if participant.phone
		}

		upcoming_classes = [
			yoga_class
			for yoga_class in root.series_queryset().filter(start_time__gte=now)
			if yoga_class.should_show_in_public_list(upcoming_limit=upcoming_limit, now=now)
		]

		for yoga_class in upcoming_classes:
			opted_out_phones = {
				phone.strip()
				for phone in yoga_class.series_prebooking_opt_outs.values_list('client__phone', flat=True)
				if phone
			}
			active_phones = {
				phone
				for phone in participants
				if phone not in opted_out_phones
			}

			yoga_class.bookings.filter(source=Booking.SOURCE_SERIES_PREBOOK).exclude(
				client_phone__in=active_phones,
			).delete()

			existing_phones = {
				(phone or '').strip()
				for phone in yoga_class.bookings.values_list('client_phone', flat=True)
				if phone
			}

			for phone, participant in participants.items():
				if phone in opted_out_phones or phone in existing_phones:
					continue
				try:
					Booking.objects.create(
						studio=yoga_class.studio,
						yoga_class=yoga_class,
						client_name=participant.name,
						client_email=participant.email,
						client_phone=phone,
						source=Booking.SOURCE_SERIES_PREBOOK,
					)
				except ValidationError:
					continue
				existing_phones.add(phone)

	def save(self, *args, **kwargs):
		if not self.studio_id:
			self.studio = Studio.get_default()
		self.start_time = self._as_aware(self.start_time)
		self.end_time = self._as_aware(self.end_time)
		self.full_clean()
		super().save(*args, **kwargs)
		if not self.recurrence_parent_id:
			self.sync_weekly_occurrences(upcoming_limit=2)
			self.sync_series_prebookings(upcoming_limit=2)


class Client(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='clients',
		db_constraint=False,
	)
	name = models.CharField(max_length=120)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=40)
	reminder_classes = models.ManyToManyField(
		YogaClass,
		blank=True,
		related_name='reminder_clients',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['name', 'phone']
		constraints = [
			models.UniqueConstraint(
				fields=['studio', 'phone'],
				condition=models.Q(phone__gt=''),
				name='unique_client_phone_per_studio',
			),
		]

	def __str__(self):
		if self.email:
			return f"{self.name} ({self.email})"
		return f"{self.name} ({self.phone})"

	def clean(self):
		self.email = (self.email or '').strip().lower()
		self.phone = (self.phone or '').strip()
		if not self.phone:
			raise ValidationError('Phone is required for clients.')

	def save(self, *args, **kwargs):
		if not self.studio_id:
			self.studio = Studio.get_default()
		self.email = (self.email or '').strip().lower()
		self.phone = (self.phone or '').strip()
		self.full_clean()
		super().save(*args, **kwargs)


class SeriesPrebookingOptOut(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='series_prebooking_opt_outs',
		db_constraint=False,
	)
	yoga_class = models.ForeignKey(
		YogaClass,
		on_delete=models.CASCADE,
		related_name='series_prebooking_opt_outs',
	)
	client = models.ForeignKey(
		Client,
		on_delete=models.CASCADE,
		related_name='series_prebooking_opt_outs',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']
		constraints = [
			models.UniqueConstraint(
				fields=['yoga_class', 'client'],
				name='unique_series_prebooking_opt_out',
			),
		]

	def clean(self):
		if self.client_id and self.yoga_class_id and self.client.studio_id != self.yoga_class.studio_id:
			raise ValidationError('Prebooking opt-outs must belong to the same studio as the class.')

		if self.studio_id and self.yoga_class_id and self.studio_id != self.yoga_class.studio_id:
			raise ValidationError('Prebooking opt-outs must belong to the same studio as the class.')

	def save(self, *args, **kwargs):
		if not self.studio_id and self.yoga_class_id:
			self.studio_id = self.yoga_class.studio_id
		elif not self.studio_id:
			self.studio = Studio.get_default()
		self.full_clean()
		super().save(*args, **kwargs)


class SmsReminderLog(models.Model):
	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='sms_logs',
		db_constraint=False,
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
	client_email = models.EmailField(blank=True)
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
	SOURCE_PUBLIC = 'public'
	SOURCE_INSTRUCTOR = 'instructor'
	SOURCE_SERIES_PREBOOK = 'series_prebook'
	SOURCE_CHOICES = [
		(SOURCE_PUBLIC, 'Public'),
		(SOURCE_INSTRUCTOR, 'Instructor'),
		(SOURCE_SERIES_PREBOOK, 'Series prebook'),
	]

	studio = models.ForeignKey(
		Studio,
		on_delete=models.PROTECT,
		related_name='bookings',
		db_constraint=False,
	)
	yoga_class = models.ForeignKey(
		YogaClass,
		on_delete=models.CASCADE,
		related_name='bookings',
	)
	client_name = models.CharField(max_length=120)
	client_email = models.EmailField(blank=True)
	client_phone = models.CharField(max_length=40)
	notes = models.TextField(blank=True)
	source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_PUBLIC)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['created_at']
		constraints = [
			models.UniqueConstraint(
				fields=['yoga_class', 'client_phone'],
				condition=models.Q(client_phone__gt=''),
				name='unique_booking_phone_per_class',
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
		current_bookings += self.yoga_class.prebooked_reservation_count(exclude_phone=self.client_phone)
		if current_bookings >= self.yoga_class.capacity:
			raise ValidationError('This class is already full.')

	def save(self, *args, **kwargs):
		if not self.studio_id and self.yoga_class_id:
			self.studio_id = self.yoga_class.studio_id
		elif not self.studio_id:
			self.studio = Studio.get_default()
		self.client_email = (self.client_email or '').strip().lower()
		self.client_phone = (self.client_phone or '').strip()
		self.full_clean()
		super().save(*args, **kwargs)
