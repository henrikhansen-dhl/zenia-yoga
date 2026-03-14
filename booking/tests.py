from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone

from .forms import BookingForm
from .models import Booking, Client, SmsReminderLog, YogaClass


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


class WeeklyRecurrenceTests(TestCase):
	def test_recurring_class_generates_next_two_upcoming_occurrences(self):
		now = timezone.now()
		root_class = YogaClass.objects.create(
			title='Thursday Flow',
			short_description='Weekly evening yoga.',
			description='A recurring class.',
			instructor_name='Zenia',
			start_time=now - timedelta(days=14),
			end_time=now - timedelta(days=14) + timedelta(hours=1),
			capacity=10,
			is_weekly_recurring=True,
			is_published=True,
		)

		root_class.sync_weekly_occurrences(upcoming_limit=2, now=now)

		future_series = list(root_class.series_queryset().filter(start_time__gte=now))
		self.assertEqual(len(future_series), 2)
		self.assertTrue(all(item.start_time >= now for item in future_series))

	def test_public_list_only_shows_next_two_upcoming_recurring_classes(self):
		now = timezone.now()
		root_class = YogaClass.objects.create(
			title='Thursday Flow',
			short_description='Weekly evening yoga.',
			description='A recurring class.',
			instructor_name='Zenia',
			start_time=now - timedelta(days=21),
			end_time=now - timedelta(days=21) + timedelta(hours=1),
			capacity=10,
			is_weekly_recurring=True,
			is_published=True,
		)
		root_class.sync_weekly_occurrences(upcoming_limit=2, now=now)

		response = self.client.get('/')

		self.assertEqual(response.status_code, 200)
		classes = response.context['classes']
		self.assertEqual(len(classes), 2)
		self.assertTrue(all(yoga_class.start_time >= now for yoga_class in classes))
		self.assertTrue(all(yoga_class.title == 'Thursday Flow' for yoga_class in classes))

	def test_recurring_class_participants_can_be_saved_from_class_detail_action(self):
		user = get_user_model().objects.create_user(
			username='series-manager',
			email='series@example.com',
			password='test-pass-123',
		)
		self.client.force_login(user)

		now = timezone.now()
		root_class = YogaClass.objects.create(
			title='Thursday Flow',
			short_description='Weekly evening yoga.',
			description='A recurring class.',
			instructor_name='Zenia',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=10,
			is_weekly_recurring=True,
			is_published=True,
		)
		participant = Client.objects.create(
			name='Mia Dahl',
			email='mia@example.com',
			phone='22446688',
		)

		response = self.client.post(
			f'/instructor/classes/{root_class.pk}/participants/',
			data={'participants': [participant.pk]},
		)

		self.assertEqual(response.status_code, 302)
		root_class.refresh_from_db()
		self.assertIn(participant, root_class.series_participants.all())

	def test_quick_add_participant_creates_client_and_attaches_to_series(self):
		user = get_user_model().objects.create_user(
			username='series-quick-add',
			email='series-quick@example.com',
			password='test-pass-123',
		)
		self.client.force_login(user)

		now = timezone.now()
		root_class = YogaClass.objects.create(
			title='Thursday Flow',
			short_description='Weekly evening yoga.',
			description='A recurring class.',
			instructor_name='Zenia',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=10,
			is_weekly_recurring=True,
			is_published=True,
		)

		response = self.client.post(
			f'/instructor/classes/{root_class.pk}/participants/add/',
			data={
				'name': 'Mette Holm',
				'email': 'mette@example.com',
				'phone': '22334455',
			},
		)

		self.assertEqual(response.status_code, 302)
		client = Client.objects.get(email='mette@example.com')
		self.assertEqual(client.name, 'Mette Holm')
		self.assertIn(client, root_class.series_participants.all())

	def test_quick_add_participant_attaches_existing_client(self):
		user = get_user_model().objects.create_user(
			username='series-quick-existing',
			email='series-existing@example.com',
			password='test-pass-123',
		)
		self.client.force_login(user)

		now = timezone.now()
		root_class = YogaClass.objects.create(
			title='Thursday Flow',
			short_description='Weekly evening yoga.',
			description='A recurring class.',
			instructor_name='Zenia',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=10,
			is_weekly_recurring=True,
			is_published=True,
		)
		existing_client = Client.objects.create(
			name='Mette Holm',
			email='mette@example.com',
			phone='99887766',
		)

		response = self.client.post(
			f'/instructor/classes/{root_class.pk}/participants/add/',
			data={
				'name': 'Mette Holm',
				'email': 'mette@example.com',
				'phone': '99887766',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Client.objects.filter(email='mette@example.com').count(), 1)
		self.assertIn(existing_client, root_class.series_participants.all())

	def test_remove_participant_detaches_from_series(self):
		user = get_user_model().objects.create_user(
			username='series-remove',
			email='series-remove@example.com',
			password='test-pass-123',
		)
		self.client.force_login(user)

		now = timezone.now()
		root_class = YogaClass.objects.create(
			title='Thursday Flow',
			short_description='Weekly evening yoga.',
			description='A recurring class.',
			instructor_name='Zenia',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=10,
			is_weekly_recurring=True,
			is_published=True,
		)
		participant = Client.objects.create(
			name='Mette Holm',
			email='mette@example.com',
			phone='22334455',
		)
		root_class.series_participants.add(participant)

		response = self.client.post(
			f'/instructor/classes/{root_class.pk}/participants/{participant.pk}/remove/',
		)

		self.assertEqual(response.status_code, 302)
		self.assertNotIn(participant, root_class.series_participants.all())


class ClientManagementViewTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username='instructor',
			email='instructor@example.com',
			password='test-pass-123',
		)
		now = timezone.now()
		self.class_one = YogaClass.objects.create(
			title='Morning Flow',
			short_description='A calm start for the day.',
			description='Class one',
			instructor_name='Elin',
			start_time=now + timedelta(days=2),
			end_time=now + timedelta(days=2, hours=1),
			capacity=10,
		)
		self.class_two = YogaClass.objects.create(
			title='Evening Flow',
			short_description='A soft evening class.',
			description='Class two',
			instructor_name='Elin',
			start_time=now + timedelta(days=3),
			end_time=now + timedelta(days=3, hours=1),
			capacity=10,
		)

		Booking.objects.create(
			yoga_class=self.class_one,
			client_name='Mira Jensen',
			client_email='mira@example.com',
			client_phone='12345678',
		)
		Booking.objects.create(
			yoga_class=self.class_two,
			client_name='Mira Jensen',
			client_email='mira@example.com',
			client_phone='12345678',
		)

	def test_client_list_requires_login(self):
		response = self.client.get('/instructor/clients/')
		self.assertEqual(response.status_code, 302)

	def test_client_list_groups_classes_by_client_email(self):
		self.client.force_login(self.user)
		response = self.client.get('/instructor/clients/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['client_count'], 1)
		clients = response.context['clients']
		self.assertEqual(clients[0]['name'], 'Mira Jensen')
		self.assertEqual(clients[0]['phone'], '12345678')
		self.assertEqual(len(clients[0]['classes']), 2)

	def test_client_list_allows_manual_client_creation_with_reminder_classes(self):
		self.client.force_login(self.user)
		response = self.client.post('/instructor/clients/', data={
			'name': 'Lina Mo',
			'email': 'lina@example.com',
			'phone': '99887766',
			'reminder_classes': [self.class_one.pk],
		})

		self.assertEqual(response.status_code, 302)
		client = Client.objects.get(email='lina@example.com')
		self.assertEqual(client.name, 'Lina Mo')
		self.assertEqual(client.phone, '99887766')
		self.assertEqual(client.reminder_classes.count(), 1)
		self.assertEqual(client.reminder_classes.first(), self.class_one)

		list_response = self.client.get('/instructor/clients/')
		self.assertEqual(list_response.status_code, 200)
		self.assertEqual(list_response.context['client_count'], 2)

	def test_export_sms_reminders_returns_csv_rows_for_manual_clients(self):
		self.client.force_login(self.user)
		client = Client.objects.create(
			name='Lina Mo',
			email='lina@example.com',
			phone='99887766',
		)
		client.reminder_classes.add(self.class_one)

		response = self.client.get('/instructor/clients/reminders/export/')

		self.assertEqual(response.status_code, 200)
		self.assertIn('text/csv', response['Content-Type'])
		content = response.content.decode('utf-8')
		self.assertIn('Lina Mo', content)
		self.assertIn('99887766', content)
		self.assertIn('Morning Flow', content)

	def test_client_edit_updates_manual_client(self):
		self.client.force_login(self.user)
		client = Client.objects.create(
			name='Lina Mo',
			email='lina@example.com',
			phone='99887766',
		)
		client.reminder_classes.add(self.class_one)

		response = self.client.post(f'/instructor/clients/{client.pk}/edit/', data={
			'name': 'Lina Madsen',
			'email': 'lina@example.com',
			'phone': '11112222',
			'reminder_classes': [self.class_two.pk],
		})

		self.assertEqual(response.status_code, 302)
		client.refresh_from_db()
		self.assertEqual(client.name, 'Lina Madsen')
		self.assertEqual(client.phone, '11112222')
		self.assertEqual(list(client.reminder_classes.all()), [self.class_two])

	def test_client_delete_removes_manual_client(self):
		self.client.force_login(self.user)
		client = Client.objects.create(
			name='Lina Mo',
			email='lina@example.com',
			phone='99887766',
		)

		response = self.client.post(f'/instructor/clients/{client.pk}/delete/')

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Client.objects.filter(pk=client.pk).exists())

	def test_client_form_reminder_labels_use_localized_time(self):
		self.client.force_login(self.user)
		response = self.client.get('/instructor/clients/')
		self.assertEqual(response.status_code, 200)

		local_start = timezone.localtime(self.class_one.start_time)
		expected_en = local_start.strftime('%b %d, %Y %H:%M')
		expected_da = local_start.strftime('%d-%m-%Y %H:%M')
		content = response.content.decode('utf-8')
		self.assertIn('Morning Flow', response.content.decode('utf-8'))
		self.assertTrue(expected_en in content or expected_da in content)

	def test_export_sms_reminders_includes_weekly_unbooked_today_participants(self):
		self.client.force_login(self.user)

		now = timezone.now()
		weekly_class = YogaClass.objects.create(
			title='Weekly Noon Flow',
			short_description='Recurring lunch class.',
			description='Recurring class for reminders.',
			instructor_name='Elin',
			start_time=now + timedelta(hours=2),
			end_time=now + timedelta(hours=3),
			capacity=8,
			is_weekly_recurring=True,
			is_published=True,
		)

		participant = Client.objects.create(
			name='Nora Flint',
			email='nora@example.com',
			phone='55667788',
		)
		weekly_class.series_participants.add(participant)

		response = self.client.get('/instructor/clients/reminders/export/')
		content = response.content.decode('utf-8')

		self.assertEqual(response.status_code, 200)
		self.assertIn('weekly_unbooked_today', content)
		self.assertIn('Nora Flint', content)
		self.assertIn('Weekly Noon Flow', content)

	def test_export_sms_reminders_excludes_weekly_participant_when_already_booked(self):
		self.client.force_login(self.user)

		now = timezone.now()
		weekly_class = YogaClass.objects.create(
			title='Weekly Noon Flow',
			short_description='Recurring lunch class.',
			description='Recurring class for reminders.',
			instructor_name='Elin',
			start_time=now + timedelta(hours=2),
			end_time=now + timedelta(hours=3),
			capacity=8,
			is_weekly_recurring=True,
			is_published=True,
		)

		participant = Client.objects.create(
			name='Nora Flint',
			email='nora@example.com',
			phone='55667788',
		)
		weekly_class.series_participants.add(participant)

		Booking.objects.create(
			yoga_class=weekly_class,
			client_name='Nora Flint',
			client_email='nora@example.com',
			client_phone='55667788',
		)

		response = self.client.get('/instructor/clients/reminders/export/')
		content = response.content.decode('utf-8')

		self.assertEqual(response.status_code, 200)
		self.assertNotIn('weekly_unbooked_today', content)

	@override_settings(
		SMS_GATEWAY_ENABLED=True,
		SMS_GATEWAY_URL='https://api.cpsms.dk/v2/send',
		SMS_GATEWAY_USERNAME='demo-user',
		SMS_GATEWAY_API_KEY='demo-key',
		SMS_GATEWAY_FROM='ZeniaYoga',
		SMS_GATEWAY_LANGUAGE='da',
	)
	@patch('booking.instructor_views.urllib_request.urlopen')
	def test_send_sms_reminders_uses_gateway_for_manual_clients(self, mock_urlopen):
		self.client.force_login(self.user)
		client = Client.objects.create(
			name='Lina Mo',
			email='lina@example.com',
			phone='99887766',
		)
		client.reminder_classes.add(self.class_one)

		mock_response = mock_urlopen.return_value.__enter__.return_value
		mock_response.read.return_value = b'{"success": [{"to": "4599887766", "cost": 1}]}'

		response = self.client.post('/instructor/clients/reminders/send/')

		self.assertEqual(response.status_code, 302)
		self.assertTrue(mock_urlopen.called)
		log = SmsReminderLog.objects.get(client_email='lina@example.com')
		self.assertEqual(log.status, SmsReminderLog.STATUS_SENT)
		self.assertEqual(log.normalized_phone, '4599887766')

	def test_send_sms_reminders_requires_gateway_config(self):
		self.client.force_login(self.user)
		response = self.client.post('/instructor/clients/reminders/send/')
		self.assertEqual(response.status_code, 302)

	@override_settings(
		SMS_GATEWAY_ENABLED=True,
		SMS_GATEWAY_URL='https://api.cpsms.dk/v2/send',
		SMS_GATEWAY_USERNAME='demo-user',
		SMS_GATEWAY_API_KEY='demo-key',
		SMS_GATEWAY_FROM='ZeniaYoga',
		SMS_GATEWAY_LANGUAGE='da',
	)
	@patch('booking.instructor_views.urllib_request.urlopen')
	def test_send_sms_reminders_logs_invalid_phone_as_failed(self, mock_urlopen):
		self.client.force_login(self.user)
		client = Client.objects.create(
			name='Lina Mo',
			email='lina@example.com',
			phone='invalid',
		)
		client.reminder_classes.add(self.class_one)

		response = self.client.post('/instructor/clients/reminders/send/')

		self.assertEqual(response.status_code, 302)
		self.assertFalse(mock_urlopen.called)
		log = SmsReminderLog.objects.get(client_email='lina@example.com')
		self.assertEqual(log.status, SmsReminderLog.STATUS_FAILED)
		self.assertEqual(log.gateway_error, 'invalid_phone')
