from django.db import migrations, models
import django.db.models.deletion


def assign_default_studio(apps, schema_editor):
	db_alias = schema_editor.connection.alias
	Studio = apps.get_model('booking', 'Studio')
	YogaClass = apps.get_model('booking', 'YogaClass')
	Client = apps.get_model('booking', 'Client')
	Booking = apps.get_model('booking', 'Booking')
	SmsReminderLog = apps.get_model('booking', 'SmsReminderLog')

	studio, _ = Studio.objects.using(db_alias).get_or_create(
		slug='zenia-yoga',
		defaults={
			'name': 'Zenia Yoga',
			'is_active': True,
		},
	)

	YogaClass.objects.using(db_alias).filter(studio__isnull=True).update(studio=studio)
	Client.objects.using(db_alias).filter(studio__isnull=True).update(studio=studio)

	bookings_to_update = []
	for booking in Booking.objects.using(db_alias).select_related('yoga_class').filter(studio__isnull=True):
		booking.studio_id = booking.yoga_class.studio_id or studio.id
		bookings_to_update.append(booking)
	if bookings_to_update:
		Booking.objects.using(db_alias).bulk_update(bookings_to_update, ['studio'])

	logs_to_update = []
	for sms_log in SmsReminderLog.objects.using(db_alias).select_related('yoga_class').filter(studio__isnull=True):
		sms_log.studio_id = sms_log.yoga_class.studio_id if sms_log.yoga_class_id else studio.id
		logs_to_update.append(sms_log)
	if logs_to_update:
		SmsReminderLog.objects.using(db_alias).bulk_update(logs_to_update, ['studio'])


class Migration(migrations.Migration):

	dependencies = [
		('booking', '0005_smsreminderlog'),
	]

	operations = [
		migrations.CreateModel(
			name='Feature',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('code', models.SlugField(max_length=80, unique=True)),
				('name', models.CharField(max_length=120)),
				('description', models.TextField(blank=True)),
				('is_active', models.BooleanField(default=True)),
				('created_at', models.DateTimeField(auto_now_add=True)),
			],
			options={
				'ordering': ['name'],
			},
		),
		migrations.CreateModel(
			name='Studio',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('name', models.CharField(max_length=140)),
				('slug', models.SlugField(max_length=160, unique=True)),
				('contact_name', models.CharField(blank=True, max_length=120)),
				('contact_email', models.EmailField(blank=True, max_length=254)),
				('contact_phone', models.CharField(blank=True, max_length=40)),
				('billing_email', models.EmailField(blank=True, max_length=254)),
				('subscription_notes', models.TextField(blank=True)),
				('is_active', models.BooleanField(default=True)),
				('created_at', models.DateTimeField(auto_now_add=True)),
				('updated_at', models.DateTimeField(auto_now=True)),
			],
			options={
				'ordering': ['name'],
			},
		),
		migrations.CreateModel(
			name='StudioFeatureAccess',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('is_enabled', models.BooleanField(default=True)),
				('enabled_at', models.DateTimeField(auto_now_add=True)),
				('feature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='studio_accesses', to='booking.feature')),
				('studio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feature_accesses', to='booking.studio')),
			],
			options={
				'ordering': ['studio__name', 'feature__name'],
			},
		),
		migrations.AddField(
			model_name='booking',
			name='studio',
			field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='bookings', to='booking.studio'),
		),
		migrations.AddField(
			model_name='client',
			name='studio',
			field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='clients', to='booking.studio'),
		),
		migrations.AddField(
			model_name='smsreminderlog',
			name='studio',
			field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sms_logs', to='booking.studio'),
		),
		migrations.AddField(
			model_name='yogaclass',
			name='studio',
			field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='classes', to='booking.studio'),
		),
		migrations.AlterField(
			model_name='client',
			name='email',
			field=models.EmailField(max_length=254),
		),
		migrations.RunPython(assign_default_studio, migrations.RunPython.noop),
		migrations.AlterField(
			model_name='booking',
			name='studio',
			field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='bookings', to='booking.studio'),
		),
		migrations.AlterField(
			model_name='client',
			name='studio',
			field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='clients', to='booking.studio'),
		),
		migrations.AlterField(
			model_name='smsreminderlog',
			name='studio',
			field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sms_logs', to='booking.studio'),
		),
		migrations.AlterField(
			model_name='yogaclass',
			name='studio',
			field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='classes', to='booking.studio'),
		),
		migrations.AddConstraint(
			model_name='client',
			constraint=models.UniqueConstraint(fields=('studio', 'email'), name='unique_client_email_per_studio'),
		),
		migrations.AddConstraint(
			model_name='studiofeatureaccess',
			constraint=models.UniqueConstraint(fields=('studio', 'feature'), name='unique_feature_access_per_studio'),
		),
	]