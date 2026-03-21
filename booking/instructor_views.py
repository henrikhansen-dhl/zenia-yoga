import csv

from django.conf import settings
from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language

from .forms import BookingForm, ClientForm, WeeklyParticipantQuickAddForm, WeeklyParticipantsForm, YogaClassForm
from .models import Booking, Client, SmsReminderLog, YogaClass
from .sms_service import build_sms_rows, dispatch_reminders, sms_gateway_ready
from .studio_access import studio_login_required


def _msg(english, danish):
    return danish if (get_language() or 'en').startswith('da') else english


def _build_sms_rows(request, now=None):
    """Thin wrapper around sms_service.build_sms_rows that derives site_url from the request."""
    site_url = request.build_absolute_uri('/')
    return build_sms_rows(request.studio, site_url=site_url, now=now)


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
    ).select_related('recurrence_parent').order_by('start_time')
    past = YogaClass.objects.filter(
        studio=studio,
        start_time__lt=now
    ).select_related('recurrence_parent').order_by('-start_time')
    context = {'studio': studio, 'upcoming': upcoming, 'past': past}
    return render(request, 'instructor/class_list.html', context)


@studio_login_required
def client_list(request):
    now = timezone.now()
    studio = request.studio
    max_classes_per_client = 15

    if request.method == 'POST':
        form = ClientForm(request.POST, studio=studio)
        if form.is_valid():
            client_phone = form.cleaned_data['phone']
            client, created = Client.objects.update_or_create(
                studio=studio,
                phone=client_phone,
                defaults={
                    'studio': studio,
                    'name': form.cleaned_data['name'],
                    'email': form.cleaned_data['email'],
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

    bookings = Booking.objects.filter(studio=studio).select_related('yoga_class').only(
        'client_name',
        'client_phone',
        'client_email',
        'created_at',
        'yoga_class_id',
        'yoga_class__title',
        'yoga_class__start_time',
    ).order_by('-yoga_class__start_time', '-created_at')

    clients_by_phone = {}
    for booking in bookings:
        key = booking.client_phone.strip() if booking.client_phone else ''
        if not key:
            key = (booking.client_email or '').strip().lower() or f'booking:{booking.pk}'

        if key not in clients_by_phone:
            clients_by_phone[key] = {
                'name': booking.client_name,
                'phone': booking.client_phone or '',
                'email': booking.client_email,
                'last_created_at': booking.created_at,
                'classes': [],
                'class_ids': set(),
                'reminder_classes': [],
                'client_id': None,
            }

        client_entry = clients_by_phone[key]
        if booking.created_at >= client_entry['last_created_at']:
            client_entry['name'] = booking.client_name
            client_entry['last_created_at'] = booking.created_at
            if booking.client_phone:
                client_entry['phone'] = booking.client_phone
            if booking.client_email:
                client_entry['email'] = booking.client_email

        if (
            booking.yoga_class_id not in client_entry['class_ids']
            and len(client_entry['class_ids']) < max_classes_per_client
        ):
            client_entry['class_ids'].add(booking.yoga_class_id)
            client_entry['classes'].append(booking.yoga_class)

    reminder_classes_qs = YogaClass.objects.filter(
        studio=studio,
        is_published=True,
        start_time__gte=now,
    ).order_by('start_time')
    manual_clients = Client.objects.filter(studio=studio).prefetch_related(
        Prefetch('reminder_classes', queryset=reminder_classes_qs, to_attr='upcoming_reminder_classes')
    ).all().order_by('name')
    for manual_client in manual_clients:
        key = manual_client.phone.strip() if manual_client.phone else ''
        if not key:
            key = (manual_client.email or '').strip().lower() or f'client:{manual_client.pk}'

        if key not in clients_by_phone:
            clients_by_phone[key] = {
                'name': manual_client.name,
                'phone': manual_client.phone or '',
                'email': manual_client.email,
                'last_created_at': manual_client.created_at,
                'classes': [],
                'class_ids': set(),
                'reminder_classes': [],
                'client_id': manual_client.pk,
            }

        client_entry = clients_by_phone[key]
        if manual_client.name:
            client_entry['name'] = manual_client.name
        if manual_client.phone:
            client_entry['phone'] = manual_client.phone
        if manual_client.email:
            client_entry['email'] = manual_client.email
        client_entry['client_id'] = manual_client.pk

        client_entry['reminder_classes'] = list(manual_client.upcoming_reminder_classes)

    clients = sorted(clients_by_phone.values(), key=lambda item: item['name'].lower())
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

    if not sms_gateway_ready():
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

    result = dispatch_reminders(rows, language=settings.SMS_GATEWAY_LANGUAGE)
    sent_count = result['sent']
    failed_count = result['failed']
    failure_examples = result['failure_examples']

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
    root_class.sync_series_prebookings(upcoming_limit=2)
    yoga_class.refresh_from_db()
    bookings = yoga_class.bookings.order_by('created_at')
    manual_booking_form = BookingForm(yoga_class=yoga_class)
    participants_form = None
    participant_quick_add_form = None
    if root_class.is_weekly_recurring:
        participants_form = WeeklyParticipantsForm(
            studio=root_class.studio,
            capacity=root_class.capacity,
            initial={
                'participants': root_class.series_participants.all(),
                'prebooked_participants': root_class.series_prebooked_participants.all(),
            },
        )
        participant_quick_add_form = WeeklyParticipantQuickAddForm()

    context = {
        'yoga_class': yoga_class,
        'bookings': bookings,
        'manual_booking_form': manual_booking_form,
        'studio_clients': Client.objects.filter(studio=request.studio).order_by('name').only('name', 'email', 'phone'),
        'participants_form': participants_form,
        'participant_quick_add_form': participant_quick_add_form,
        'series_participants': root_class.series_participants.all().order_by('name') if root_class.is_weekly_recurring else [],
        'series_prebooked_participants': root_class.series_prebooked_participants.all().order_by('name') if root_class.is_weekly_recurring else [],
        'series_upcoming': [
            yoga_item
            for yoga_item in root_class.series_queryset().filter(start_time__gte=timezone.now())
            if yoga_item.should_show_in_public_list(upcoming_limit=2)
        ] if root_class.is_weekly_recurring else [],
    }
    return render(request, 'instructor/class_detail.html', context)


@studio_login_required
def class_booking_add(request, pk):
    yoga_class = get_object_or_404(YogaClass, pk=pk, studio=request.studio)

    if request.method != 'POST':
        return redirect('instructor:class_detail', pk=yoga_class.pk)

    form = BookingForm(request.POST, yoga_class=yoga_class)
    if form.is_valid():
        booking = form.save(commit=False)
        booking.studio = request.studio
        booking.source = Booking.SOURCE_INSTRUCTOR
        booking.save()
        prebooked_client = yoga_class.prebooked_participant_by_phone(booking.client_phone)
        if prebooked_client:
            yoga_class.clear_prebooked_client_opt_out(prebooked_client)
        messages.success(
            request,
            _msg(
                f'Booking for {booking.client_name} has been added.',
                f'Booking for {booking.client_name} er tilfoejet.',
            ),
        )
    else:
        first_error = next(iter(form.errors.values()))[0] if form.errors else _msg('Invalid form data.', 'Ugyldige formulardata.')
        messages.error(request, first_error)

    return redirect('instructor:class_detail', pk=yoga_class.pk)


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
        form = WeeklyParticipantsForm(request.POST, studio=root_class.studio, capacity=root_class.capacity)
        if form.is_valid():
            root_class.series_participants.set(form.cleaned_data['participants'])
            root_class.series_prebooked_participants.set(form.cleaned_data['prebooked_participants'])
            root_class.sync_series_prebookings(upcoming_limit=2)
            messages.success(
                request,
                _msg('Weekly registrations have been updated.', 'Ugentlige registreringer er opdateret.'),
            )
        else:
            first_error = next(iter(form.non_field_errors()), None) or (
                next(iter(form.errors.values()))[0] if form.errors else _msg('Invalid form data.', 'Ugyldige formulardata.')
            )
            messages.error(request, first_error)

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
                phone=phone,
                defaults={
                    'studio': root_class.studio,
                    'name': name,
                    'email': email,
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
                if email != client.email:
                    client.email = email
                    changed = True
                if changed:
                    client.save()

            registration_type = form.cleaned_data['registration_type']
            if registration_type == WeeklyParticipantQuickAddForm.TYPE_PREBOOKED:
                if (
                    not root_class.series_prebooked_participants.filter(pk=client.pk).exists()
                    and root_class.series_prebooked_participants.count() >= root_class.capacity
                ):
                    messages.error(
                        request,
                        _msg(
                            f'This class already has {root_class.capacity} prebooked participants, which matches its capacity.',
                            f'Dette hold har allerede {root_class.capacity} forudbookede deltagere, som svarer til kapaciteten.',
                        ),
                    )
                    return redirect('instructor:class_detail', pk=yoga_class.pk)
                root_class.series_prebooked_participants.add(client)
                root_class.series_participants.remove(client)
                root_class.sync_series_prebookings(upcoming_limit=2)
                success_message = _msg(
                    f'"{client.name}" has been added as prebooked in the weekly series.',
                    f'"{client.name}" er tilføjet som forudbooket i den ugentlige serie.',
                )
            else:
                root_class.series_participants.add(client)
                root_class.series_prebooked_participants.remove(client)
                root_class.sync_series_prebookings(upcoming_limit=2)
                success_message = _msg(
                    f'"{client.name}" has been added to weekly reminders.',
                    f'"{client.name}" er tilføjet til ugentlige påmindelser.',
                )
            messages.success(
                request,
                success_message,
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
        root_class.series_prebooked_participants.remove(client)
        root_class.sync_series_prebookings(upcoming_limit=2)
        messages.success(
            request,
            _msg(
                f'"{client.name}" has been removed from weekly registration.',
                f'"{client.name}" er fjernet fra den ugentlige registrering.',
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
        prebooked_client = booking.yoga_class.prebooked_participant_by_phone(booking.client_phone)
        if prebooked_client:
            booking.yoga_class.mark_prebooked_client_opted_out(prebooked_client)
        booking.delete()
        messages.success(
            request,
            _msg(f'Booking for {name} has been removed.', f'Booking for {name} er fjernet.'),
        )
    return redirect('instructor:class_detail', pk=class_pk)
