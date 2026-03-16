import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import translation
from django.utils import timezone

from .db_router import StudioDatabaseRouter
from .middleware import StudioContextMiddleware
from .forms import BookingForm, YogaClassForm
from .models import Booking, Client, Feature, SmsReminderLog, Studio, StudioFeatureAccess, StudioInvoice, StudioMembership, YogaClass
from .studio_db import deactivate_studio, set_current_studio_alias


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
		self.class_detail_url = reverse(
			'booking:class_detail',
			kwargs={'studio_slug': self.yoga_class.studio.slug, 'pk': self.yoga_class.pk},
		)
		self.class_list_url = reverse('booking:class_list', kwargs={'studio_slug': self.yoga_class.studio.slug})

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

	def test_successful_booking_redirects_to_public_class_list(self):
		response = self.client.post(
			self.class_detail_url,
			data={
				'client_name': 'Asta',
				'client_email': 'asta@example.com',
				'client_phone': '12345678',
				'notes': '',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers['Location'], self.class_list_url)
		self.assertTrue(
			Booking.objects.filter(
				yoga_class=self.yoga_class,
				client_email='asta@example.com',
			).exists()
		)

	def test_successful_booking_shows_prominent_confirmation_on_front_page(self):
		response = self.client.post(
			self.class_detail_url,
			data={
				'client_name': 'Asta',
				'client_email': 'asta@example.com',
				'client_phone': '12345678',
				'notes': '',
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'booking-success-banner')
		self.assertContains(response, 'booking-success-title')
		self.assertContains(response, 'booking-success-text')

	def test_public_class_list_shows_studio_logo_in_header(self):
		logo_bytes = (
			b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
			b'\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00'
			b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
		)
		with tempfile.TemporaryDirectory() as media_root:
			with override_settings(MEDIA_ROOT=media_root):
				self.yoga_class.studio.logo = SimpleUploadedFile('studio.gif', logo_bytes, content_type='image/gif')
				self.yoga_class.studio.save()

				response = self.client.get(self.class_list_url)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'public-studio-badge-image')
		self.assertContains(response, '/media/studio-logos/studio')


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

		response = self.client.get(
			reverse('booking:class_list', kwargs={'studio_slug': root_class.studio.slug})
		)

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


class InstructorClassFormTests(TestCase):
	def test_danish_edit_form_renders_iso_value_for_date_input(self):
		now = timezone.now() + timedelta(days=2)
		yoga_class = YogaClass(
			title='Torsdag aften yoga',
			short_description='Zen Yoga',
			description='Beskrivelse',
			instructor_name='Zenia',
			start_time=now,
			end_time=now + timedelta(hours=1),
			capacity=10,
		)

		with translation.override('da'):
			form = YogaClassForm(instance=yoga_class)

		self.assertIn('type="date"', str(form['start_time'].subwidgets[0]))
		self.assertIn(
			f'value="{timezone.localtime(now):%Y-%m-%d}"',
			str(form['start_time'].subwidgets[0]),
		)

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


class InstructorShellTests(TestCase):
	def test_instructor_layout_uses_post_logout_form(self):
		user = get_user_model().objects.create_user(
			username='shell-user',
			email='shell-user@example.com',
			password='test-pass-123',
		)
		self.client.force_login(user)

		response = self.client.get('/instructor/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'action="/admin/logout/"', html=False)
		self.assertContains(response, 'method="post"', html=False)
		self.assertNotContains(response, '/admin/logout/?next=/')


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
		SMS_GATEWAY_FROM='YogaStudioPlatform',
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
		SMS_GATEWAY_FROM='YogaStudioPlatform',
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


class StudioPlatformTests(TestCase):
	def setUp(self):
		self.superuser = get_user_model().objects.create_superuser(
			username='platform-admin',
			email='platform@example.com',
			password='test-pass-123',
		)
		self.feature = Feature.objects.create(
			code='sms-reminders',
			name='SMS Reminders',
			description='Send reminder messages before class.',
		)

	def test_studio_admin_studio_list_requires_superuser(self):
		response = self.client.get('/studio/studios/')
		self.assertEqual(response.status_code, 302)

	def test_legacy_platform_url_redirects_to_studio_url(self):
		response = self.client.get('/platform/studios/')
		self.assertEqual(response.status_code, 301)
		self.assertEqual(response.headers['Location'], '/studio/studios/')

	def test_legacy_studios_root_redirects_to_studio_studios(self):
		response = self.client.get('/studios')
		self.assertEqual(response.status_code, 301)
		self.assertEqual(response.headers['Location'], '/studio/studios/')

	def test_superuser_can_create_studio_and_enable_feature(self):
		self.client.force_login(self.superuser)

		response = self.client.post('/studio/studios/new/', data={
			'name': 'North Studio',
			'slug': 'north-studio',
			'contact_name': 'Ava North',
			'contact_email': 'ava@north.example.com',
			'contact_phone': '12345678',
			'billing_email': 'billing@north.example.com',
			'subscription_notes': 'Pays for SMS reminders.',
			'is_active': 'on',
			'enabled_features': [self.feature.pk],
		})

		self.assertEqual(response.status_code, 302)
		studio = Studio.objects.get(slug='north-studio')
		self.assertEqual(response.headers['Location'], f'/studio/studios/{studio.pk}/edit/')
		self.assertEqual(studio.name, 'North Studio')
		self.assertTrue(
			StudioFeatureAccess.objects.filter(
				studio=studio,
				feature=self.feature,
				is_enabled=True,
			).exists()
		)

	def test_studio_create_shows_db_provision_success_message(self):
		self.client.force_login(self.superuser)

		response = self.client.post('/studio/studios/new/', data={
			'name': 'West Studio',
			'slug': 'west-studio',
			'is_active': 'on',
		}, follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(
			(
				'Studio database is ready.' in response.content.decode('utf-8')
				or 'Studiets database er klargjort.' in response.content.decode('utf-8')
			)
		)

	def test_studio_edit_page_shows_public_booking_url(self):
		self.client.force_login(self.superuser)
		studio = Studio.objects.create(name='North Studio', slug='north-studio')

		response = self.client.get(f'/studio/studios/{studio.pk}/edit/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'http://testserver/studios/north-studio/')
		self.assertContains(response, 'data-copy-url="http://testserver/studios/north-studio/"', html=False)

	def test_studio_list_shows_public_booking_url_and_copy_action(self):
		self.client.force_login(self.superuser)
		studio = Studio.objects.create(name='North Studio', slug='north-studio')

		response = self.client.get('/studio/studios/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'http://testserver/studios/north-studio/')
		self.assertContains(response, 'data-copy-url="http://testserver/studios/north-studio/"', html=False)

	def test_superuser_can_create_studio_membership(self):
		self.client.force_login(self.superuser)
		studio = Studio.get_default()
		staff_user = get_user_model().objects.create_user(
			username='studio-staff',
			email='staff@example.com',
			password='test-pass-123',
		)

		response = self.client.post('/studio/access/new/', data={
			'studio': studio.pk,
			'user': staff_user.pk,
			'role': StudioMembership.ROLE_MANAGER,
			'is_active': 'on',
		})

		self.assertEqual(response.status_code, 302)
		self.assertTrue(
			StudioMembership.objects.filter(
				studio=studio,
				user=staff_user,
				is_active=True,
			).exists()
		)

	def test_clients_can_share_email_across_studios(self):
		other_studio = Studio.objects.create(name='South Studio', slug='south-studio')
		Client.objects.create(name='Lina One', email='lina@example.com')
		Client.objects.create(name='Lina Two', email='lina@example.com', studio=other_studio)

		self.assertEqual(Client.objects.filter(email='lina@example.com').count(), 2)

	def test_public_class_list_only_shows_default_studio_classes(self):
		default_studio = Studio.get_default()
		other_studio = Studio.objects.create(name='South Studio', slug='south-studio')
		now = timezone.now()

		YogaClass.objects.create(
			studio=default_studio,
			title='Default Studio Flow',
			short_description='Visible on the default site.',
			description='Default studio class.',
			instructor_name='Elin',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=10,
			is_published=True,
		)
		YogaClass.objects.create(
			studio=other_studio,
			title='Other Studio Flow',
			short_description='Should not appear on the default site.',
			description='Other studio class.',
			instructor_name='Mira',
			start_time=now + timedelta(days=1),
			end_time=now + timedelta(days=1, hours=1),
			capacity=10,
			is_published=True,
		)

		response = self.client.get(
			reverse('booking:class_list', kwargs={'studio_slug': default_studio.slug})
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Default Studio Flow')
		self.assertNotContains(response, 'Other Studio Flow')


class InstructorStudioAccessTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username='studio-manager',
			email='manager@example.com',
			password='test-pass-123',
		)
		self.default_studio = Studio.get_default()
		self.other_studio = Studio.objects.create(name='South Studio', slug='south-studio')
		StudioMembership.objects.create(
			studio=self.other_studio,
			user=self.user,
			role=StudioMembership.ROLE_MANAGER,
		)
		self.now = timezone.now()
		self.other_class = YogaClass.objects.create(
			studio=self.other_studio,
			title='South Flow',
			short_description='Scoped to south studio.',
			description='Studio-specific class.',
			instructor_name='Mira',
			start_time=self.now + timedelta(days=1),
			end_time=self.now + timedelta(days=1, hours=1),
			capacity=10,
			is_published=True,
		)
		self.default_class = YogaClass.objects.create(
			studio=self.default_studio,
			title='Default Flow',
			short_description='Scoped to default studio.',
			description='Default studio class.',
			instructor_name='Elin',
			start_time=self.now + timedelta(days=1),
			end_time=self.now + timedelta(days=1, hours=1),
			capacity=10,
			is_published=True,
		)

	def test_instructor_dashboard_uses_membership_studio(self):
		self.client.force_login(self.user)

		response = self.client.get('/instructor/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'South Flow')
		self.assertNotContains(response, 'Default Flow')

	def test_instructor_class_create_uses_membership_studio(self):
		self.client.force_login(self.user)

		response = self.client.post('/instructor/classes/new/', data={
			'title': 'Studio Managed Flow',
			'short_description': 'Created by studio manager.',
			'description': 'New scoped class.',
			'instructor_name': 'Mira',
			'start_time_0': (self.now + timedelta(days=3)).date().isoformat(),
			'start_time_1': '09:00',
			'end_time_0': (self.now + timedelta(days=3)).date().isoformat(),
			'end_time_1': '10:00',
			'capacity': 12,
			'location': 'South Room',
			'focus': 'Mobility',
			'is_published': 'on',
		})

		self.assertEqual(response.status_code, 302)
		created = YogaClass.objects.get(title='Studio Managed Flow')
		self.assertEqual(created.studio, self.other_studio)

	def test_user_without_studio_membership_is_denied(self):
		unassigned_user = get_user_model().objects.create_user(
			username='no-studio',
			email='no-studio@example.com',
			password='test-pass-123',
		)
		self.client.force_login(unassigned_user)

		response = self.client.get('/instructor/')

		self.assertEqual(response.status_code, 403)

	def test_instructor_sidebar_shows_studio_logo(self):
		self.client.force_login(self.user)
		logo_bytes = (
			b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
			b'\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00'
			b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
		)
		with tempfile.TemporaryDirectory() as media_root:
			with override_settings(MEDIA_ROOT=media_root):
				self.other_studio.logo = SimpleUploadedFile('south.gif', logo_bytes, content_type='image/gif')
				self.other_studio.save()

				response = self.client.get('/instructor/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'studio-badge-image')
		self.assertContains(response, '/media/studio-logos/south')


class DatabaseRoutingTests(SimpleTestCase):
	def test_booking_platform_models_route_to_default(self):
		router = StudioDatabaseRouter()
		self.assertEqual(router.db_for_read(Studio), 'default')
		self.assertEqual(router.db_for_write(Studio), 'default')

	def test_studio_models_route_to_active_studio_alias(self):
		router = StudioDatabaseRouter()
		set_current_studio_alias('studio_north_studio')
		try:
			self.assertEqual(router.db_for_read(YogaClass), 'studio_north_studio')
			self.assertEqual(router.db_for_write(Client), 'studio_north_studio')
		finally:
			deactivate_studio()

	def test_studio_db_disallows_runpython_and_platform_models(self):
		router = StudioDatabaseRouter()
		self.assertFalse(router.allow_migrate('studio_north_studio', 'booking', model_name=None))
		self.assertFalse(router.allow_migrate('studio_north_studio', 'booking', model_name='studio'))
		self.assertFalse(router.allow_migrate('studio_north_studio', 'booking', model_name='yogaclass'))


class StudioContextMiddlewareTests(SimpleTestCase):
	def test_middleware_clears_context_after_request(self):
		request_factory = RequestFactory()

		set_current_studio_alias('studio_temp_studio')
		self.assertEqual(StudioDatabaseRouter().db_for_read(YogaClass), 'studio_temp_studio')

		middleware = StudioContextMiddleware(lambda request: None)
		middleware(request_factory.get('/instructor/'))

		self.assertEqual(StudioDatabaseRouter().db_for_read(YogaClass), 'default')


class StudioPortalTests(TestCase):
	def setUp(self):
		self.owner = get_user_model().objects.create_user(
			username='studio-owner',
			email='owner@example.com',
			password='test-pass-123',
			is_staff=True,
		)
		self.studio = Studio.get_default()
		StudioMembership.objects.create(
			studio=self.studio,
			user=self.owner,
			role=StudioMembership.ROLE_OWNER,
		)

	def test_login_page_is_available(self):
		response = self.client.get('/studio/login/')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Studio')

	def test_owner_can_create_employee_access(self):
		self.client.force_login(self.owner)
		response = self.client.post('/studio/employees/new/', data={
			'username': 'new-employee',
			'email': 'employee@example.com',
			'first_name': 'New',
			'last_name': 'Employee',
			'password': 'new-pass-123',
			'role': StudioMembership.ROLE_STAFF,
			'is_active': 'on',
		})

		self.assertEqual(response.status_code, 302)
		self.assertTrue(get_user_model().objects.filter(username='new-employee').exists())
		self.assertTrue(
			StudioMembership.objects.filter(
				studio=self.studio,
				user__username='new-employee',
				role=StudioMembership.ROLE_STAFF,
			).exists()
		)

	def test_owner_can_create_invoice_from_usage(self):
		self.client.force_login(self.owner)
		feature = Feature.objects.create(code='sms-reminders', name='SMS Reminders')
		StudioFeatureAccess.objects.create(studio=self.studio, feature=feature, is_enabled=True)
		SmsReminderLog.objects.create(
			studio=self.studio,
			client_name='Mia',
			client_email='mia@example.com',
			message_text='Reminder',
			class_title='Morning Flow',
			reminder_reason='manual_class_interest',
			status=SmsReminderLog.STATUS_SENT,
		)

		today = timezone.localdate()
		response = self.client.post('/studio/invoices/new/', data={
			'period_start': (today - timedelta(days=1)).isoformat(),
			'period_end': (today + timedelta(days=1)).isoformat(),
			'subscription_fee': '100.00',
			'employee_fee': '50.00',
			'sms_fee': '2.50',
			'notes': 'Monthly service invoice',
		})

		self.assertEqual(response.status_code, 302)
		invoice = StudioInvoice.objects.get(studio=self.studio)
		self.assertEqual(invoice.lines.count(), 3)
