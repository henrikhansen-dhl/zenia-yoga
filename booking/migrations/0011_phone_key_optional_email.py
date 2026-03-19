from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0010_add_studio_portal_invoices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='client_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name='booking',
            name='client_phone',
            field=models.CharField(max_length=40),
        ),
        migrations.AlterField(
            model_name='client',
            name='email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name='client',
            name='phone',
            field=models.CharField(max_length=40),
        ),
        migrations.AlterField(
            model_name='smsreminderlog',
            name='client_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.RemoveConstraint(
            model_name='booking',
            name='unique_booking_email_per_class',
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.UniqueConstraint(
                condition=models.Q(client_phone__gt=''),
                fields=('yoga_class', 'client_phone'),
                name='unique_booking_phone_per_class',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='client',
            name='unique_client_email_per_studio',
        ),
        migrations.AddConstraint(
            model_name='client',
            constraint=models.UniqueConstraint(
                condition=models.Q(phone__gt=''),
                fields=('studio', 'phone'),
                name='unique_client_phone_per_studio',
            ),
        ),
        migrations.AlterModelOptions(
            name='client',
            options={'ordering': ['name', 'phone']},
        ),
    ]
