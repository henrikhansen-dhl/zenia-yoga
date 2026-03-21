from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('booking', '0012_userauthenticatordevice'),
	]

	operations = [
		migrations.AddField(
			model_name='booking',
			name='source',
			field=models.CharField(
				choices=[('public', 'Public'), ('instructor', 'Instructor'), ('series_prebook', 'Series prebook')],
				default='public',
				max_length=20,
			),
		),
		migrations.AddField(
			model_name='yogaclass',
			name='series_prebooked_participants',
			field=models.ManyToManyField(blank=True, related_name='weekly_prebooked_series_classes', to='booking.client'),
		),
		migrations.CreateModel(
			name='SeriesPrebookingOptOut',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('created_at', models.DateTimeField(auto_now_add=True)),
				('client', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='series_prebooking_opt_outs', to='booking.client')),
				('studio', models.ForeignKey(db_constraint=False, on_delete=models.deletion.PROTECT, related_name='series_prebooking_opt_outs', to='booking.studio')),
				('yoga_class', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='series_prebooking_opt_outs', to='booking.yogaclass')),
			],
			options={
				'ordering': ['-created_at'],
			},
		),
		migrations.AddConstraint(
			model_name='seriesprebookingoptout',
			constraint=models.UniqueConstraint(fields=('yoga_class', 'client'), name='unique_series_prebooking_opt_out'),
		),
	]