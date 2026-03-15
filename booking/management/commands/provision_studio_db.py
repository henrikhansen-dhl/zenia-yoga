"""
Management command: provision_studio_db

Creates and migrates the per-studio database for one or all studios.

Usage
-----
# Provision a specific studio:
python manage.py provision_studio_db <studio-slug>

# Provision every studio:
python manage.py provision_studio_db --all
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create and migrate the per-studio database for a studio.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            'studio_slug',
            nargs='?',
            type=str,
            help='Slug of the studio whose database should be provisioned.',
        )
        group.add_argument(
            '--all',
            action='store_true',
            dest='all_studios',
            help='Provision databases for every studio.',
        )

    def handle(self, *args, **options):
        from booking.models import Studio
        from booking.studio_db import provision_studio_database

        if options['all_studios']:
            studios = list(Studio.objects.all())
            if not studios:
                self.stdout.write('No studios found.')
                return
        else:
            slug = options['studio_slug']
            try:
                studios = [Studio.objects.get(slug=slug)]
            except Studio.DoesNotExist:
                raise CommandError(f'No studio with slug "{slug}" exists.')

        for studio in studios:
            alias = provision_studio_database(
                studio.slug,
                verbosity=options.get('verbosity', 1),
            )
            self.stdout.write(f'Provisioning "{studio.name}" → {alias} …')
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ {studio.name} provisioned.')
            )
