from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('booking', '0002_yogaclass_weekly_recurrence'),
	]

	operations = [
		migrations.CreateModel(
			name='Client',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('name', models.CharField(max_length=120)),
				('email', models.EmailField(max_length=254, unique=True)),
				('phone', models.CharField(blank=True, max_length=40)),
				('created_at', models.DateTimeField(auto_now_add=True)),
			],
			options={
				'ordering': ['name', 'email'],
			},
		),
		migrations.AddField(
			model_name='client',
			name='reminder_classes',
			field=models.ManyToManyField(blank=True, related_name='reminder_clients', to='booking.yogaclass'),
		),
	]