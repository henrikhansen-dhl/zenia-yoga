from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .forms import BookingForm
from .models import Booking, YogaClass


class BookingFlowTests(TestCase):
	def setUp(self):
		now = timezone.now()
		self.yoga_class = YogaClass.objects.create(
			title='Morning Flow',
			short_description='A calm start for the day.',
			description='Breath-led movement and grounding stillness.',
			instructor_name='Elin',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=1,
			location='Studio One',
			focus='Breath and balance',
		)

	def test_form_rejects_duplicate_email_for_same_class(self):
		Booking.objects.create(
			yoga_class=self.yoga_class,
			client_name='Mira',
			client_email='mira@example.com',
		)

		form = BookingForm(
			data={
				'client_name': 'Mira Again',
				'client_email': 'mira@example.com',
				'client_phone': '',
				'notes': '',
			},
			yoga_class=self.yoga_class,
		)

		self.assertFalse(form.is_valid())

	def test_booking_clean_rejects_full_class(self):
		Booking.objects.create(
			yoga_class=self.yoga_class,
			client_name='Mira',
			client_email='mira@example.com',
		)

		booking = Booking(
			yoga_class=self.yoga_class,
			client_name='Nova',
			client_email='nova@example.com',
		)

		with self.assertRaises(ValidationError):
			booking.full_clean()
