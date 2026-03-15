import sys

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Studio
from .studio_db import provision_studio_database


@receiver(post_save, sender=Studio, weak=False, dispatch_uid='booking.provision_studio_database_on_create')
def provision_studio_database_on_create(sender, instance, created, **kwargs):
    if not created:
        return

    # Skip expensive per-studio migration work in test runs.
    if 'test' in sys.argv:
        return

    if getattr(settings, 'STUDIO_AUTO_PROVISION_ON_CREATE', True):
        provision_studio_database(instance.slug, verbosity=0)
