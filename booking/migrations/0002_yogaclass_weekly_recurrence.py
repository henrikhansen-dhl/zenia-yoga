from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('booking', '0001_initial'),
	]

	operations = [
		migrations.AddField(
			model_name='yogaclass',
			name='is_weekly_recurring',
			field=models.BooleanField(default=False),
		),
		migrations.AddField(
			model_name='yogaclass',
			name='recurrence_parent',
			field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name='generated_occurrences', to='booking.yogaclass'),
		),
		migrations.AddConstraint(
			model_name='yogaclass',
			constraint=models.UniqueConstraint(fields=('recurrence_parent', 'start_time'), name='unique_recurring_occurrence_start'),
		),
	]