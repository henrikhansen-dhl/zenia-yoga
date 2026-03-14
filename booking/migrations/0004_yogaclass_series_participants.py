from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('booking', '0003_client'),
	]

	operations = [
		migrations.AddField(
			model_name='yogaclass',
			name='series_participants',
			field=models.ManyToManyField(blank=True, related_name='weekly_series_classes', to='booking.client'),
		),
	]
