"""
SMS reminder service — shared logic used by both the instructor views
and the ``send_daily_reminders`` management command.

All functions here are request-free so they can be called from a
scheduled task without an HTTP context.
"""
import base64
import hashlib
import json
import re
from urllib import error, request as urllib_request

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


# ---------------------------------------------------------------------------
# Phone normalisation
# ---------------------------------------------------------------------------

def normalize_phone(raw_phone: str) -> str:
    """Return a normalized E.164-style phone number string (digits only with country code)."""
    digits = re.sub(r'\D', '', raw_phone or '')
    if not digits:
        return ''
    if digits.startswith('00'):
        digits = digits[2:]
    if raw_phone and str(raw_phone).strip().startswith('+'):
        return digits
    if len(digits) == 8:
        return f'{settings.SMS_GATEWAY_DEFAULT_COUNTRY_CODE}{digits}'
    return digits


# ---------------------------------------------------------------------------
# Gateway helpers
# ---------------------------------------------------------------------------

def sms_gateway_ready() -> bool:
    return (
        settings.SMS_GATEWAY_ENABLED
        and settings.SMS_GATEWAY_URL
        and settings.SMS_GATEWAY_USERNAME
        and settings.SMS_GATEWAY_API_KEY
        and settings.SMS_GATEWAY_FROM
    )


def send_sms_via_cpsms(phone: str, message_text: str, reference: str) -> tuple[bool, str]:
    """
    Send a single SMS via the CPSMS gateway.

    Returns ``(True, '')`` on success or ``(False, error_text)`` on failure.
    """
    gateway_username = settings.SMS_GATEWAY_USERNAME
    gateway_api_key = settings.SMS_GATEWAY_API_KEY
    auth_token = f'{gateway_username}:{gateway_api_key}'.encode('utf-8')
    encoded_auth = base64.b64encode(auth_token).decode('ascii')

    payload = {
        'to': phone,
        'message': message_text,
        'from': settings.SMS_GATEWAY_FROM,
        'encoding': 'UTF-8',
        'reference': reference,
    }

    req = urllib_request.Request(
        settings.SMS_GATEWAY_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Basic {encoded_auth}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urllib_request.urlopen(req, timeout=settings.SMS_GATEWAY_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode('utf-8')
            parsed = json.loads(body) if body else {}
            if parsed.get('success'):
                return True, ''
            if parsed.get('error'):
                err = parsed['error']
                if isinstance(err, list):
                    err_text = '; '.join(str(item.get('message', item)) for item in err)
                elif isinstance(err, dict):
                    err_text = str(err.get('message', err))
                else:
                    err_text = str(err)
                return False, err_text
            return False, 'Gateway returned an unexpected response.'
    except error.HTTPError as exc:
        try:
            error_body = exc.read().decode('utf-8')
        except Exception:
            error_body = ''
        return False, f'HTTP {exc.code}: {error_body or exc.reason}'
    except error.URLError as exc:
        return False, f'Connection error: {exc.reason}'


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def build_sms_rows(studio, site_url: str, now=None) -> list[dict]:
    """
    Return a list of reminder dicts for *studio*.

    Two kinds of reminders are included:

    1. **Class-interest reminders** – clients whose ``reminder_classes``
       M2M includes an upcoming published class (start_time ≥ now).

     2. **Weekly "today" reminders** – clients in a weekly reminder list
         (``series_participants``) whose class is happening *today* and
       who have not yet booked a spot.

    ``site_url``  Full base URL used to build booking links, e.g.
                  ``"https://yourstudio.pythonanywhere.com"``.
                  Trailing slash is stripped automatically.
    """
    from .models import Booking, Client, YogaClass  # avoid circular import at module level

    site_url = site_url.rstrip('/')
    now = now or timezone.now()
    rows: list[dict] = []
    exported: set = set()

    # --- 1. Class-interest reminders -----------------------------------------
    clients = (
        Client.objects.filter(studio=studio)
        .prefetch_related('reminder_classes')
        .order_by('name')
    )
    for client in clients:
        if not client.phone:
            continue

        upcoming_classes = client.reminder_classes.filter(
            studio=studio,
            is_published=True,
            start_time__gte=now,
        ).order_by('start_time')

        for yoga_class in upcoming_classes:
            client_key = normalize_phone(client.phone) or (client.email or '').lower()
            export_key = (client_key, yoga_class.pk)
            if export_key in exported:
                continue

            class_start_local = timezone.localtime(yoga_class.start_time)
            class_start_text = class_start_local.strftime('%d-%m-%Y %H:%M')
            booking_link = site_url + reverse(
                'booking:class_detail',
                kwargs={'studio_slug': yoga_class.studio.slug, 'pk': yoga_class.pk},
            )

            sms_da = (
                f"Hej {client.name}, husk at reservere din plads til {yoga_class.title} "
                f"den {class_start_text}. Book her: {booking_link}"
            )
            sms_en = (
                f"Hi {client.name}, remember to reserve your seat for {yoga_class.title} "
                f"on {class_start_text}. Book here: {booking_link}"
            )

            rows.append({
                'client_name': client.name,
                'phone': client.phone,
                'email': client.email,
                'class_title': yoga_class.title,
                'class_start': class_start_text,
                'booking_link': booking_link,
                'reminder_reason': 'manual_class_interest',
                'sms_message_da': sms_da,
                'sms_message_en': sms_en,
                'class_pk': yoga_class.pk,
                'studio_id': yoga_class.studio_id,
            })
            exported.add(export_key)

    # --- 2. Weekly "today" unbooked reminders --------------------------------
    today_local_date = timezone.localdate(now)
    recurring_classes = (
        YogaClass.objects.filter(studio=studio, is_published=True, start_time__gte=now)
        .select_related('recurrence_parent')
        .prefetch_related('bookings')
    )

    for yoga_class in recurring_classes:
        root_class = yoga_class.recurrence_root
        if not root_class.is_weekly_recurring:
            continue

        if timezone.localtime(yoga_class.start_time).date() != today_local_date:
            continue

        if yoga_class.spots_left <= 0:
            continue

        booked_phone_keys = {
            normalize_phone(booking.client_phone) or (booking.client_email or '').strip().lower()
            for booking in yoga_class.bookings.all()
        }

        for participant in root_class.series_participants.all():
            if not participant.phone:
                continue
            participant_key = normalize_phone(participant.phone) or (participant.email or '').lower()
            if participant_key in booked_phone_keys:
                continue

            export_key = (participant_key, yoga_class.pk)
            if export_key in exported:
                continue

            class_start_local = timezone.localtime(yoga_class.start_time)
            class_start_text = class_start_local.strftime('%d-%m-%Y %H:%M')
            booking_link = site_url + reverse(
                'booking:class_detail',
                kwargs={'studio_slug': yoga_class.studio.slug, 'pk': yoga_class.pk},
            )

            sms_da = (
                f"Hej {participant.name}, holdet {yoga_class.title} er i dag kl. {class_start_local:%H:%M}. "
                f"Husk at reservere din plads: {booking_link}"
            )
            sms_en = (
                f"Hi {participant.name}, {yoga_class.title} is today at {class_start_local:%H:%M}. "
                f"Remember to reserve your seat: {booking_link}"
            )

            rows.append({
                'client_name': participant.name,
                'phone': participant.phone,
                'email': participant.email,
                'class_title': yoga_class.title,
                'class_start': class_start_text,
                'booking_link': booking_link,
                'reminder_reason': 'weekly_unbooked_today',
                'sms_message_da': sms_da,
                'sms_message_en': sms_en,
                'class_pk': yoga_class.pk,
                'studio_id': yoga_class.studio_id,
            })
            exported.add(export_key)

    return rows


# ---------------------------------------------------------------------------
# Bulk send + log
# ---------------------------------------------------------------------------

def dispatch_reminders(rows: list[dict], language: str = 'da') -> dict:
    """
    Send SMS for each row and create ``SmsReminderLog`` records.

    Returns a summary dict::

        {
            'sent': <int>,
            'failed': <int>,
            'skipped': <int>,    # rows with no valid phone
            'failure_examples': [<str>, ...],   # up to 3 entries
        }
    """
    from .models import SmsReminderLog  # avoid circular import

    language = (language or 'da').lower()
    sent = 0
    failed = 0
    skipped = 0
    failure_examples: list[str] = []
    logs_to_create: list[SmsReminderLog] = []

    for row in rows:
        normalized = normalize_phone(row['phone'])
        message_text = row['sms_message_da'] if language == 'da' else row['sms_message_en']
        email_hash = hashlib.sha1((row['email'] or '').lower().encode('utf-8')).hexdigest()[:10]
        reference = f"z{row['class_pk']}-{email_hash}"

        if not normalized:
            skipped += 1
            failed += 1
            if len(failure_examples) < 3:
                failure_examples.append(f"{row['client_name']}: invalid phone")
            logs_to_create.append(SmsReminderLog(
                studio_id=row['studio_id'],
                yoga_class_id=row['class_pk'],
                client_name=row['client_name'],
                client_email=row['email'],
                raw_phone=row['phone'],
                normalized_phone='',
                message_language=language,
                message_text=message_text,
                class_title=row['class_title'],
                reminder_reason=row['reminder_reason'],
                status=SmsReminderLog.STATUS_FAILED,
                gateway_reference=reference,
                gateway_error='invalid_phone',
            ))
            continue

        success, error_text = send_sms_via_cpsms(normalized, message_text, reference)
        status = SmsReminderLog.STATUS_SENT if success else SmsReminderLog.STATUS_FAILED
        if success:
            sent += 1
        else:
            failed += 1
            if len(failure_examples) < 3:
                failure_examples.append(f"{row['client_name']}: {error_text}")

        logs_to_create.append(SmsReminderLog(
            studio_id=row['studio_id'],
            yoga_class_id=row['class_pk'],
            client_name=row['client_name'],
            client_email=row['email'],
            raw_phone=row['phone'],
            normalized_phone=normalized,
            message_language=language,
            message_text=message_text,
            class_title=row['class_title'],
            reminder_reason=row['reminder_reason'],
            status=status,
            gateway_reference=reference,
            gateway_error='' if success else error_text,
        ))

    if logs_to_create:
        SmsReminderLog.objects.bulk_create(logs_to_create)

    return {
        'sent': sent,
        'failed': failed,
        'skipped': skipped,
        'failure_examples': failure_examples,
    }
