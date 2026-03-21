from django.core.management.base import BaseCommand, CommandError

from booking.studio_db import get_studio_migration_status


class Command(BaseCommand):
    help = 'Report studio databases that are behind on booking migrations.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--studio',
            metavar='SLUG',
            help='Slug of the studio to inspect, e.g. zenia-yoga.',
        )
        group.add_argument(
            '--all',
            action='store_true',
            dest='all_studios',
            help='Inspect every studio database.',
        )
        parser.add_argument(
            '--fail-on-drift',
            action='store_true',
            help='Exit with an error if any studio database has pending migrations.',
        )

    def handle(self, *args, **options):
        from booking.models import Studio

        if options['all_studios']:
            studios = list(Studio.objects.all().order_by('name'))
            if not studios:
                self.stdout.write('No studios found.')
                return
        else:
            slug = options['studio']
            try:
                studios = [Studio.objects.get(slug=slug)]
            except Studio.DoesNotExist:
                raise CommandError(f'No studio with slug "{slug}" exists.')

        behind_count = 0

        for studio in studios:
            status = get_studio_migration_status(studio.slug)
            pending = status['pending_migrations']
            self.stdout.write(f'[{studio.name}] {studio.slug} → {status["alias"]}')
            self.stdout.write(f'  DB: {status["database_name"]}')
            if pending:
                behind_count += 1
                self.stdout.write(self.style.WARNING(f'  Pending booking migrations: {", ".join(pending)}'))
            else:
                self.stdout.write(self.style.SUCCESS('  Up to date.'))

        if behind_count:
            summary = f'{behind_count} studio database(s) are behind on booking migrations.'
            if options['fail_on_drift']:
                raise CommandError(summary)
            self.stdout.write(self.style.WARNING(summary))
            return

        self.stdout.write(self.style.SUCCESS('All inspected studio databases are up to date.'))