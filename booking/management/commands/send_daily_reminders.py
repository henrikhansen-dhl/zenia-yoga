"""
Management command: send_daily_reminders

Sends SMS reminders for today's weekly classes and upcoming class-interest
reminders, without requiring an HTTP request.  Designed to be run from a
PythonAnywhere scheduled task — one task per studio.

Usage
-----
# Send SMS for a specific studio (dry-run first to preview):
python manage.py send_daily_reminders --studio zenia-yoga --dry-run

# Actually send:
python manage.py send_daily_reminders --studio zenia-yoga

# Run for all active studios (useful for a single global cron):
python manage.py send_daily_reminders --all

PythonAnywhere scheduled task command (example):
    /home/<username>/.virtualenvs/<venv>/bin/python \\
        /home/<username>/<project>/manage.py \\
        send_daily_reminders --studio zenia-yoga
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Send daily SMS reminders for a studio without an HTTP request.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--studio',
            metavar='SLUG',
            help='Slug of the studio to send reminders for, e.g. zenia-yoga',
        )
        group.add_argument(
            '--all',
            action='store_true',
            dest='all_studios',
            help='Send reminders for every active studio.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print who would receive a reminder without actually sending SMS.',
        )
        parser.add_argument(
            '--lang',
            default=None,
            metavar='LANG',
            help='Language for SMS text: "da" or "en". Defaults to SMS_GATEWAY_LANGUAGE setting.',
        )

    def handle(self, *args, **options):
        from booking.models import Studio
        from booking.sms_service import build_sms_rows, dispatch_reminders, sms_gateway_ready
        from booking.studio_db import activate_studio, deactivate_studio

        dry_run: bool = options['dry_run']
        language: str = (options['lang'] or settings.SMS_GATEWAY_LANGUAGE).lower()
        site_url: str = settings.SITE_URL

        if not dry_run and not sms_gateway_ready():
            raise CommandError(
                'SMS gateway is not configured. Set SMS_GATEWAY_ENABLED=True '
                'and supply SMS_GATEWAY_USERNAME, SMS_GATEWAY_API_KEY, SMS_GATEWAY_FROM '
                'in your environment variables.'
            )

        if options['all_studios']:
            studios = list(Studio.objects.filter(is_active=True))
            if not studios:
                self.stdout.write('No active studios found.')
                return
        else:
            slug = options['studio']
            try:
                studios = [Studio.objects.get(slug=slug)]
            except Studio.DoesNotExist:
                raise CommandError(f'No studio with slug "{slug}" exists.')

        for studio in studios:
            activate_studio(studio.slug)
            try:
                self._process_studio(studio, site_url, language, dry_run, build_sms_rows, dispatch_reminders)
            finally:
                deactivate_studio()

    def _process_studio(self, studio, site_url, language, dry_run, build_sms_rows, dispatch_reminders):
        now = timezone.now()
        local_now = timezone.localtime(now)
        self.stdout.write(
            f'\n[{studio.name}]  {local_now:%Y-%m-%d %H:%M %Z}'
        )

        rows = build_sms_rows(studio, site_url=site_url, now=now)

        if not rows:
            self.stdout.write('  No reminders to send today.')
            return

        if dry_run:
            self.stdout.write(f'  DRY RUN — {len(rows)} reminder(s) would be sent:')
            for row in rows:
                self.stdout.write(
                    f"    • {row['client_name']} ({row['phone']})  →  "
                    f"{row['class_title']} at {row['class_start']}  "
                    f"[{row['reminder_reason']}]"
                )
            return

        self.stdout.write(f'  Sending {len(rows)} reminder(s)…')
        result = dispatch_reminders(rows, language=language)

        sent = result['sent']
        failed = result['failed']
        examples = result['failure_examples']

        if sent:
            self.stdout.write(self.style.SUCCESS(f'  ✓ Sent: {sent}'))
        if failed:
            extra = f"  ({'; '.join(examples)})" if examples else ''
            self.stdout.write(self.style.ERROR(f'  ✗ Failed: {failed}{extra}'))
