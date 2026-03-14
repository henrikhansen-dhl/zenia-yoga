from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0007_studiomembership'),
    ]

    operations = [
        migrations.AddField(
            model_name='studio',
            name='logo',
            field=models.ImageField(blank=True, upload_to='studio-logos/'),
        ),
    ]