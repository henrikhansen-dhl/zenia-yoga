from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_yogaclass_series_participants'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmsReminderLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_name', models.CharField(max_length=120)),
                ('client_email', models.EmailField(max_length=254)),
                ('raw_phone', models.CharField(blank=True, max_length=40)),
                ('normalized_phone', models.CharField(blank=True, max_length=40)),
                ('message_language', models.CharField(default='da', max_length=5)),
                ('message_text', models.TextField()),
                ('class_title', models.CharField(max_length=120)),
                ('reminder_reason', models.CharField(max_length=60)),
                ('status', models.CharField(choices=[('sent', 'Sent'), ('failed', 'Failed'), ('skipped', 'Skipped')], max_length=10)),
                ('gateway_reference', models.CharField(blank=True, max_length=32)),
                ('gateway_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('yoga_class', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='sms_logs', to='booking.yogaclass')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
