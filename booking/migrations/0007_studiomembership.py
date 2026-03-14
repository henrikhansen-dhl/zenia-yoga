from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

	dependencies = [
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
		('booking', '0006_platform_studios'),
	]

	operations = [
		migrations.CreateModel(
			name='StudioMembership',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('role', models.CharField(choices=[('owner', 'Owner'), ('manager', 'Manager'), ('staff', 'Staff')], default='manager', max_length=20)),
				('is_active', models.BooleanField(default=True)),
				('created_at', models.DateTimeField(auto_now_add=True)),
				('studio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='booking.studio')),
				('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='studio_memberships', to=settings.AUTH_USER_MODEL)),
			],
			options={
				'ordering': ['studio__name', 'user__username'],
			},
		),
		migrations.AddConstraint(
			model_name='studiomembership',
			constraint=models.UniqueConstraint(fields=('studio', 'user'), name='unique_studio_membership_per_user'),
		),
	]