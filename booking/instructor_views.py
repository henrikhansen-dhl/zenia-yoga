import csv
import base64
import hashlib
import json
import re
from urllib import error, request as urllib_request

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language

from .forms import ClientForm, WeeklyParticipantQuickAddForm, WeeklyParticipantsForm, YogaClassForm
from .models import Booking, Client, SmsReminderLog, YogaClass
from .studio_access import studio_login_required


def _msg(english, danish):
    return danish if (get_language() or 'en').startswith('da') else english


def _normalize_phone(raw_phone):
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


def _build_sms_rows(request, now=None):
    now = now or timezone.now()
    studio = request.studio
    rows = []
    exported = set()

    clients = Client.objects.filter(studio=studio).prefetch_related('reminder_classes').all().order_by('name')
    for client in clients:
        if not client.phone:
            continue

        upcoming_classes = client.reminder_classes.filter(
            studio=studio,
            is_published=True,
            start_time__gte=now,
        ).order_by('start_time')

        for yoga_class in upcoming_classes:
            export_key = (client.email.lower(), yoga_class.pk)
            if export_key in exported:
                continue

            class_start_local = timezone.localtime(yoga_class.start_time)
            class_start_text = class_start_local.strftime('%d-%m-%Y %H:%M')
            booking_link = request.build_absolute_uri(
                reverse('booking:class_detail', kwargs={'studio_slug': yoga_class.studio.slug, 'pk': yoga_class.pk})
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

    today_local_date = timezone.localdate(now)
    recurring_classes = YogaClass.objects.filter(
        studio=studio,
        is_published=True,
        start_time__gte=now,
    ).select_related('recurrence_parent').prefetch_related('bookings')

    for yoga_class in recurring_classes:
        root_class = yoga_class.recurrence_root
        if not root_class.is_weekly_recurring:
            continue

        if timezone.localtime(yoga_class.start_time).date() != today_local_date:
            continue

        if yoga_class.spots_left <= 0:
            continue

        booked_emails = {
            booking.client_email.strip().lower()
            for booking in yoga_class.bookings.all()
        }

        for participant in root_class.series_participants.all():
            if not participant.phone:
                continue
            if participant.email.lower() in booked_emails:
                continue

            export_key = (participant.email.lower(), yoga_class.pk)
            if export_key in exported:
                continue

            class_start_local = timezone.localtime(yoga_class.start_time)
            class_start_text = class_start_local.strftime('%d-%m-%Y %H:%M')
            booking_link = request.build_absolute_uri(
                reverse('booking:class_detail', kwargs={'studio_slug': yoga_class.studio.slug, 'pk': yoga_class.pk})
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


def _send_sms_via_cpsms(phone, message_text, reference):
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


def _sms_gateway_ready():
    return (
        settings.SMS_GATEWAY_ENABLED
        and settings.SMS_GATEWAY_URL
        and settings.SMS_GATEWAY_USERNAME
        and settings.SMS_GATEWAY_API_KEY
        and settings.SMS_GATEWAY_FROM
    )


@studio_login_required
def dashboard(request):
    now = timezone.now()
    studio = request.studio
    YogaClass.sync_all_weekly_occurrences(upcoming_limit=2, now=now)
    upcoming = YogaClass.objects.filter(studio=studio, start_time__gte=now).order_by('start_time')
    past = YogaClass.objects.filter(studio=studio, start_time__lt=now).order_by('-start_time')
    total_bookings = Booking.objects.filter(studio=studio).count()
    total_classes = YogaClass.objects.filter(studio=studio).count()
    context = {
        'studio': studio,
        'upcoming': upcoming,
        'past': past,
        'total_bookings': total_bookings,
        'total_classes': total_classes,
        'upcoming_count': upcoming.count(),
    }
    return render(request, 'instructor/dashboard.html', context)


@studio_login_required
def class_list(request):
    now = timezone.now()
    studio = request.studio
    YogaClass.sync_all_weekly_occurrences(upcoming_limit=2, now=now)
    upcoming = YogaClass.objects.filter(
        studio=studio,
        start_time__gte=now
    ).order_by('start_time')
    past = YogaClass.objects.filter(
        studio=studio,
        start_time__lt=now
    ).order_by('-start_time')
    context = {'studio': studio, 'upcoming': upcoming, 'past': past}
    return render(request, 'instructor/class_list.html', context)


@studio_login_required
def client_list(request):
    now = timezone.now()
    studio = request.studio

    if request.method == 'POST':
        form = ClientForm(request.POST, studio=studio)
        if form.is_valid():
            client_email = form.cleaned_data['email']
            client, created = Client.objects.update_or_create(
                studio=studio,
                email=client_email,
                defaults={
                    'studio': studio,
                    'name': form.cleaned_data['name'],
                    'phone': form.cleaned_data['phone'],
                },
            )
            client.reminder_classes.set(form.cleaned_data['reminder_classes'])
            messages.success(
                request,
                _msg(
                    f'Client "{client.name}" has been saved.',
                    f'Klient "{client.name}" er gemt.',
                ),
            )
            return redirect('instructor:client_list')
    else:
        form = ClientForm(studio=studio)

    bookings = Booking.objects.filter(studio=studio).select_related('yoga_class').order_by(
        'client_name',
        'created_at',
        'yoga_class__start_time',
    )

    clients_by_email = {}
    for booking in bookings:
        key = booking.client_email.strip().lower()
        if key not in clients_by_email:
            clients_by_email[key] = {
                'name': booking.client_name,
                'phone': booking.client_phone or '',
                'email': booking.client_email,
                'last_created_at': booking.created_at,
                'classes': [],
                'class_ids': set(),
                'reminder_classes': [],
                'client_id': None,
            }

        client_entry = clients_by_email[key]
        if booking.created_at >= client_entry['last_created_at']:
            client_entry['name'] = booking.client_name
            client_entry['last_created_at'] = booking.created_at
            if booking.client_phone:
                client_entry['phone'] = booking.client_phone

        if booking.yoga_class_id not in client_entry['class_ids']:
            client_entry['class_ids'].add(booking.yoga_class_id)
            client_entry['classes'].append(booking.yoga_class)

    manual_clients = Client.objects.filter(studio=studio).prefetch_related('reminder_classes').all().order_by('name')
    for manual_client in manual_clients:
        key = manual_client.email.strip().lower()
        if key not in clients_by_email:
            clients_by_email[key] = {
                'name': manual_client.name,
                'phone': manual_client.phone or '',
                'email': manual_client.email,
                'last_created_at': manual_client.created_at,
                'classes': [],
                'class_ids': set(),
                'reminder_classes': [],
                'client_id': manual_client.pk,
            }

        client_entry = clients_by_email[key]
        if manual_client.name:
            client_entry['name'] = manual_client.name
        if manual_client.phone:
            client_entry['phone'] = manual_client.phone
        client_entry['client_id'] = manual_client.pk

        client_entry['reminder_classes'] = list(
            manual_client.reminder_classes.filter(
                is_published=True,
                start_time__gte=now,
            ).order_by('start_time')
        )

    clients = sorted(clients_by_email.values(), key=lambda item: item['name'].lower())
    for client in clients:
        client.pop('class_ids', None)

    context = {
        'clients': clients,
        'client_count': len(clients),
        'form': form,
        'recent_sms_logs': SmsReminderLog.objects.filter(studio=studio).select_related('yoga_class').all()[:20],
        'studio': studio,
    }
    return render(request, 'instructor/client_list.html', context)


@studio_login_required
def client_edit(request, pk):
    studio = request.studio
    client = get_object_or_404(Client, pk=pk, studio=studio)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client, studio=studio)
        if form.is_valid():
            client = form.save()
            messages.success(
                request,
                _msg(
                    f'Client "{client.name}" has been updated.',
                    f'Klient "{client.name}" er opdateret.',
                ),
            )
            return redirect('instructor:client_list')
    else:
        form = ClientForm(instance=client, studio=studio)

    context = {
        'form': form,
        'client': client,
        'action': _msg('Save changes', 'Gem ændringer'),
    }
    return render(request, 'instructor/client_form.html', context)


@studio_login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk, studio=request.studio)
    if request.method == 'POST':
        client_name = client.name
        client.delete()
        messages.success(
            request,
            _msg(
                f'Client "{client_name}" has been deleted.',
                f'Klient "{client_name}" er slettet.',
            ),
        )
        return redirect('instructor:client_list')

    context = {
        'client': client,
    }
    return render(request, 'instructor/client_confirm_delete.html', context)


@studio_login_required
def export_sms_reminders(request):
    rows = _build_sms_rows(request)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="sms_reminders.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'client_name',
        'phone',
        'email',
        'class_title',
        'class_start',
        'booking_link',
        'reminder_reason',
        'sms_message_da',
        'sms_message_en',
    ])

    for row in rows:
        writer.writerow([
            row['client_name'],
            row['phone'],
            row['email'],
            row['class_title'],
            row['class_start'],
            row['booking_link'],
            row['reminder_reason'],
            row['sms_message_da'],
            row['sms_message_en'],
        ])

    return response


@studio_login_required
def send_sms_reminders(request):
    if request.method != 'POST':
        return redirect('instructor:client_list')

    if not _sms_gateway_ready():
        messages.error(
            request,
            _msg(
                'SMS gateway is not configured. Add SMS settings in environment variables first.',
                'SMS-gateway er ikke konfigureret. Tilfoej SMS-indstillinger i miljoevariabler foerst.',
            ),
        )
        return redirect('instructor:client_list')

    rows = _build_sms_rows(request)
    if not rows:
        messages.warning(
            request,
            _msg('No reminders to send right now.', 'Ingen paamindelser at sende lige nu.'),
        )
        return redirect('instructor:client_list')

    language = settings.SMS_GATEWAY_LANGUAGE.lower()
    sent_count = 0
    failed_count = 0
    failure_examples = []
    logs_to_create = []

    for row in rows:
        normalized_phone = _normalize_phone(row['phone'])
        message_text = row['sms_message_da'] if language == 'da' else row['sms_message_en']
        email_hash = hashlib.sha1(row['email'].lower().encode('utf-8')).hexdigest()[:10]
        reference = f"z{row['class_pk']}-{email_hash}"

        if not normalized_phone:
            failed_count += 1
            if len(failure_examples) < 3:
                failure_examples.append(f"{row['client_name']}: invalid phone")
            logs_to_create.append(
                SmsReminderLog(
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
                )
            )
            continue

        success, error_text = _send_sms_via_cpsms(normalized_phone, message_text, reference)
        if success:
            sent_count += 1
            logs_to_create.append(
                SmsReminderLog(
                    studio_id=row['studio_id'],
                    yoga_class_id=row['class_pk'],
                    client_name=row['client_name'],
                    client_email=row['email'],
                    raw_phone=row['phone'],
                    normalized_phone=normalized_phone,
                    message_language=language,
                    message_text=message_text,
                    class_title=row['class_title'],
                    reminder_reason=row['reminder_reason'],
                    status=SmsReminderLog.STATUS_SENT,
                    gateway_reference=reference,
                    gateway_error='',
                )
            )
        else:
            failed_count += 1
            if len(failure_examples) < 3:
                failure_examples.append(f"{row['client_name']}: {error_text}")
            logs_to_create.append(
                SmsReminderLog(
                    studio_id=row['studio_id'],
                    yoga_class_id=row['class_pk'],
                    client_name=row['client_name'],
                    client_email=row['email'],
                    raw_phone=row['phone'],
                    normalized_phone=normalized_phone,
                    message_language=language,
                    message_text=message_text,
                    class_title=row['class_title'],
                    reminder_reason=row['reminder_reason'],
                    status=SmsReminderLog.STATUS_FAILED,
                    gateway_reference=reference,
                    gateway_error=error_text,
                )
            )

    if logs_to_create:
        SmsReminderLog.objects.bulk_create(logs_to_create)

    if sent_count:
        messages.success(
            request,
            _msg(
                f'SMS reminders sent: {sent_count}.',
                f'SMS-paamindelser sendt: {sent_count}.',
            ),
        )

    if failed_count:
        extra = f" ({'; '.join(failure_examples)})" if failure_examples else ''
        messages.error(
            request,
            _msg(
                f'SMS failed for {failed_count} reminder(s){extra}',
                f'SMS fejlede for {failed_count} paamindelse(r){extra}',
            ),
        )

    return redirect('instructor:client_list')


@studio_login_required
def class_create(request):
    studio = request.studio
    if request.method == 'POST':
        form = YogaClassForm(request.POST, request.FILES)
        if form.is_valid():
            yoga_class = form.save(commit=False)
            yoga_class.studio = studio
            yoga_class.save()
            yoga_class.sync_weekly_occurrences(upcoming_limit=2)
            messages.success(
                request,
                _msg(f'"{yoga_class.title}" has been created.', f'"{yoga_class.title}" er oprettet.'),
            )
            return redirect('instructor:class_detail', pk=yoga_class.pk)
    else:
        form = YogaClassForm()
    return render(request, 'instructor/class_form.html', {
        'form': form,
        'action': _msg('Create class', 'Opret hold'),
    })


@studio_login_required
def class_detail(request, pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
    yoga_class.sync_weekly_occurrences(upcoming_limit=2)
    root_class = yoga_class.recurrence_root
    bookings = yoga_class.bookings.order_by('created_at')
    participants_form = None
    participant_quick_add_form = None
    if root_class.is_weekly_recurring:
        participants_form = WeeklyParticipantsForm(
            studio=root_class.studio,
            initial={'participants': root_class.series_participants.all()},
        )
        participant_quick_add_form = WeeklyParticipantQuickAddForm()

    context = {
        'yoga_class': yoga_class,
        'bookings': bookings,
        'participants_form': participants_form,
        'participant_quick_add_form': participant_quick_add_form,
        'series_participants': root_class.series_participants.all().order_by('name') if root_class.is_weekly_recurring else [],
        'series_upcoming': [
            yoga_item
            for yoga_item in root_class.series_queryset().filter(start_time__gte=timezone.now())
            if yoga_item.should_show_in_public_list(upcoming_limit=2)
        ] if root_class.is_weekly_recurring else [],
    }
    return render(request, 'instructor/class_detail.html', context)


@studio_login_required
def class_participants_update(request, pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
    root_class = yoga_class.recurrence_root

    if not root_class.is_weekly_recurring:
        messages.error(
            request,
            _msg('Participants can only be managed for weekly classes.', 'Deltagere kan kun styres for ugentlige hold.'),
        )
        return redirect('instructor:class_detail', pk=yoga_class.pk)

    if request.method == 'POST':
        form = WeeklyParticipantsForm(request.POST, studio=root_class.studio)
        if form.is_valid():
            root_class.series_participants.set(form.cleaned_data['participants'])
            messages.success(
                request,
                _msg('Weekly participants have been updated.', 'Ugentlige deltagere er opdateret.'),
            )

    return redirect('instructor:class_detail', pk=yoga_class.pk)


@studio_login_required
def class_participant_quick_add(request, pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
    root_class = yoga_class.recurrence_root

    if not root_class.is_weekly_recurring:
        messages.error(
            request,
            _msg('Participants can only be managed for weekly classes.', 'Deltagere kan kun styres for ugentlige hold.'),
        )
        return redirect('instructor:class_detail', pk=yoga_class.pk)

    if request.method == 'POST':
        form = WeeklyParticipantQuickAddForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            name = form.cleaned_data['name']
            phone = form.cleaned_data['phone']

            client, created = Client.objects.get_or_create(
                studio=root_class.studio,
                email=email,
                defaults={
                    'studio': root_class.studio,
                    'name': name,
                    'phone': phone,
                },
            )

            if not created:
                changed = False
                if name and name != client.name:
                    client.name = name
                    changed = True
                if phone and phone != client.phone:
                    client.phone = phone
                    changed = True
                if changed:
                    client.save()

            root_class.series_participants.add(client)
            messages.success(
                request,
                _msg(
                    f'"{client.name}" has been added to weekly participants.',
                    f'"{client.name}" er tilføjet til ugentlige deltagere.',
                ),
            )
        else:
            first_error = next(iter(form.errors.values()))[0] if form.errors else _msg('Invalid form data.', 'Ugyldige formulardata.')
            messages.error(request, first_error)

    return redirect('instructor:class_detail', pk=yoga_class.pk)


@studio_login_required
def class_participant_remove(request, pk, client_pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
    root_class = yoga_class.recurrence_root

    if not root_class.is_weekly_recurring:
        messages.error(
            request,
            _msg('Participants can only be managed for weekly classes.', 'Deltagere kan kun styres for ugentlige hold.'),
        )
        return redirect('instructor:class_detail', pk=yoga_class.pk)

    if request.method == 'POST':
        client = get_object_or_404(Client, pk=client_pk, studio=root_class.studio)
        root_class.series_participants.remove(client)
        messages.success(
            request,
            _msg(
                f'"{client.name}" has been removed from weekly participants.',
                f'"{client.name}" er fjernet fra ugentlige deltagere.',
            ),
        )

    return redirect('instructor:class_detail', pk=yoga_class.pk)


@studio_login_required
def class_edit(request, pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
    if request.method == 'POST':
        form = YogaClassForm(request.POST, request.FILES, instance=yoga_class)
        if form.is_valid():
            yoga_class = form.save()
            yoga_class.sync_weekly_occurrences(upcoming_limit=2)
            messages.success(
                request,
                _msg(f'"{yoga_class.title}" has been updated.', f'"{yoga_class.title}" er opdateret.'),
            )
            return redirect('instructor:class_detail', pk=yoga_class.pk)
    else:
        form = YogaClassForm(instance=yoga_class)
    return render(request, 'instructor/class_form.html', {
        'form': form,
        'action': _msg('Save changes', 'Gem ændringer'),
        'yoga_class': yoga_class,
    })


@studio_login_required
def class_toggle_publish(request, pk):
    if request.method == 'POST':
        yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
        yoga_class.is_published = not yoga_class.is_published
        yoga_class.save(update_fields=['is_published'])
        state = _msg('published', 'udgivet') if yoga_class.is_published else _msg('unpublished', 'afpubliceret')
        messages.success(request, f'"{yoga_class.title}" {_msg("is now", "er nu")} {state}.')
    return redirect('instructor:class_detail', pk=pk)


@studio_login_required
def class_delete(request, pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)
    if request.method == 'POST':
        title = yoga_class.title
        yoga_class.delete()
        messages.success(request, _msg(f'"{title}" has been deleted.', f'"{title}" er slettet.'))
        return redirect('instructor:class_list')
    return render(request, 'instructor/confirm_delete.html', {
        'object_name': yoga_class.title,
        'cancel_url': reverse('instructor:class_detail', args=[yoga_class.pk]),
    })


@studio_login_required
def booking_delete(request, pk):
    booking = get_object_or_404(Booking, pk=pk, studio=request.studio)
    class_pk = booking.yoga_class_id
    if request.method == 'POST':
        name = booking.client_name
        booking.delete()
        messages.success(
            request,
            _msg(f'Booking for {name} has been removed.', f'Booking for {name} er fjernet.'),
        )
    return redirect('instructor:class_detail', pk=class_pk)
