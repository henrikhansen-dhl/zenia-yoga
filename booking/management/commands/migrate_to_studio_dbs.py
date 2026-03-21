"""
Management command: migrate_to_studio_dbs

Copies per-studio data (YogaClass, Booking, Client, SmsReminderLog and their
M2M through-tables) from the default (platform) database into each studio's
dedicated database.

Run this once after first enabling the per-studio database split on an
existing installation.

Usage
-----
# Migrate all studios (keeps source data in default DB by default):
python manage.py migrate_to_studio_dbs

# Migrate a single studio:
python manage.py migrate_to_studio_dbs --studio <slug>

# Remove source rows from the default DB after copying:
python manage.py migrate_to_studio_dbs --delete-source
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Copy per-studio data from the default database to each studio database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--studio',
            type=str,
            dest='studio_slug',
            help='Only migrate data for this studio slug.',
        )
        parser.add_argument(
            '--delete-source',
            action='store_true',
            dest='delete_source',
            help='Delete the copied rows from the default database after migration.',
        )

    def handle(self, *args, **options):
        from booking.models import Booking, Client, SeriesPrebookingOptOut, SmsReminderLog, Studio, YogaClass
        from booking.studio_db import provision_studio_database

        studio_slug = options.get('studio_slug')
        delete_source = options.get('delete_source', False)

        if studio_slug:
            studios = Studio.objects.filter(slug=studio_slug)
            if not studios.exists():
                self.stderr.write(self.style.ERROR(f'Studio "{studio_slug}" not found.'))
                return
        else:
            studios = Studio.objects.all()

        for studio in studios:
            self.stdout.write(f'\nMigrating data for studio: {studio.name} ({studio.slug})')

            # Ensure the target database exists and has the schema.
            alias = provision_studio_database(studio.slug, verbosity=0)

            # ── YogaClass (parents before children for FK ordering) ──────────
            parents = list(
                YogaClass.objects.using('default')
                .filter(studio=studio, recurrence_parent__isnull=True)
            )
            children = list(
                YogaClass.objects.using('default')
                .filter(studio=studio, recurrence_parent__isnull=False)
            )
            _bulk_copy(YogaClass, parents, alias, self.stdout)
            _bulk_copy(YogaClass, children, alias, self.stdout)
            self.stdout.write(f'  YogaClass: {len(parents) + len(children)} rows')

            # ── Client ───────────────────────────────────────────────────────
            clients = list(Client.objects.using('default').filter(studio=studio))
            _bulk_copy(Client, clients, alias, self.stdout)
            self.stdout.write(f'  Client: {len(clients)} rows')

            # ── M2M: YogaClass.series_participants ───────────────────────────
            SeriesThrough = YogaClass.series_participants.through
            class_ids = list(
                YogaClass.objects.using('default')
                .filter(studio=studio)
                .values_list('id', flat=True)
            )
            series_rows = list(
                SeriesThrough.objects.using('default').filter(yogaclass_id__in=class_ids)
            )
            _bulk_copy(SeriesThrough, series_rows, alias, self.stdout)
            self.stdout.write(f'  YogaClass.series_participants M2M: {len(series_rows)} rows')

            PrebookedThrough = YogaClass.series_prebooked_participants.through
            prebooked_rows = list(
                PrebookedThrough.objects.using('default').filter(yogaclass_id__in=class_ids)
            )
            _bulk_copy(PrebookedThrough, prebooked_rows, alias, self.stdout)
            self.stdout.write(f'  YogaClass.series_prebooked_participants M2M: {len(prebooked_rows)} rows')

            # ── M2M: Client.reminder_classes ─────────────────────────────────
            RemindersThrough = Client.reminder_classes.through
            client_ids = list(
                Client.objects.using('default')
                .filter(studio=studio)
                .values_list('id', flat=True)
            )
            reminder_rows = list(
                RemindersThrough.objects.using('default').filter(client_id__in=client_ids)
            )
            _bulk_copy(RemindersThrough, reminder_rows, alias, self.stdout)
            self.stdout.write(f'  Client.reminder_classes M2M: {len(reminder_rows)} rows')

            # ── Booking ───────────────────────────────────────────────────────
            bookings = list(Booking.objects.using('default').filter(studio=studio))
            _bulk_copy(Booking, bookings, alias, self.stdout)
            self.stdout.write(f'  Booking: {len(bookings)} rows')

            opt_outs = list(SeriesPrebookingOptOut.objects.using('default').filter(studio=studio))
            _bulk_copy(SeriesPrebookingOptOut, opt_outs, alias, self.stdout)
            self.stdout.write(f'  SeriesPrebookingOptOut: {len(opt_outs)} rows')

            # ── SmsReminderLog ────────────────────────────────────────────────
            logs = list(SmsReminderLog.objects.using('default').filter(studio=studio))
            _bulk_copy(SmsReminderLog, logs, alias, self.stdout)
            self.stdout.write(f'  SmsReminderLog: {len(logs)} rows')

            # ── Optional: remove source data ──────────────────────────────────
            if delete_source:
                SmsReminderLog.objects.using('default').filter(studio=studio).delete()
                Booking.objects.using('default').filter(studio=studio).delete()
                RemindersThrough.objects.using('default').filter(client_id__in=client_ids).delete()
                SeriesThrough.objects.using('default').filter(yogaclass_id__in=class_ids).delete()
                Client.objects.using('default').filter(studio=studio).delete()
                YogaClass.objects.using('default').filter(studio=studio).delete()
                self.stdout.write('  Source rows deleted from default DB.')

            self.stdout.write(self.style.SUCCESS(f'  Done: {studio.name}'))

        self.stdout.write(self.style.SUCCESS('\nMigration complete.'))


def _bulk_copy(model, objects, alias, stdout):
    """
    Insert *objects* (fetched from another DB) into *alias*, preserving PKs.
    Uses ignore_conflicts so re-running the command is safe.
    """
    for obj in objects:
        # Reset Django's internal DB-tracking so bulk_create targets *alias*.
        obj._state.db = alias
        obj._state.adding = True
    if objects:
        model.objects.using(alias).bulk_create(objects, ignore_conflicts=True)
