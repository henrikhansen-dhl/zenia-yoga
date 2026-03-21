from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language

from .forms import BookingForm, PublicUnbookingForm
from .models import Booking, Studio, YogaClass
from .studio_db import STUDIO_DB_PREFIX, activate_studio, register_all_studio_dbs


def _public_studio(studio_slug=None):
	if studio_slug:
		return get_object_or_404(Studio, slug=studio_slug, is_active=True)
	return Studio.get_default()


def default_class_list_redirect(request):
	studios = Studio.objects.filter(is_active=True).order_by('name')
	default_studio = Studio.get_default()
	context = {
		'studios': studios,
		'default_studio': default_studio,
	}
	return render(request, 'booking/public_home.html', context)


def legacy_class_detail_redirect(request, pk):
	# Search every registered studio database for this class (legacy URLs
	# pre-date the per-studio routing, so we don't know which DB to look in).
	from django.conf import settings
	register_all_studio_dbs()
	for alias in list(settings.DATABASES):
		if not alias.startswith(STUDIO_DB_PREFIX):
			continue
		try:
			yoga_class = (
				YogaClass.objects.using(alias)
				.select_related('studio')
				.get(pk=pk, is_published=True)
			)
			return redirect(
				'booking:class_detail',
				studio_slug=yoga_class.studio.slug,
				pk=yoga_class.pk,
			)
		except YogaClass.DoesNotExist:
			continue
	raise Http404


def class_list(request, studio_slug):
	now = timezone.now()
	studio = _public_studio(studio_slug)
	activate_studio(studio)
	request.studio = studio
	YogaClass.sync_all_weekly_occurrences(upcoming_limit=2, now=now)
	classes = [
		yoga_class
		for yoga_class in YogaClass.objects.filter(
		studio=studio,
		is_published=True,
		start_time__gte=now,
		).order_by('start_time')
		if yoga_class.should_show_in_public_list(upcoming_limit=2, now=now)
	]
	featured_class = classes[0] if classes else None
	context = {
		'classes': classes,
		'featured_class': featured_class,
		'studio': studio,
	}
	return render(request, 'booking/class_list.html', context)


def class_detail(request, studio_slug, pk):
	studio = _public_studio(studio_slug)
	activate_studio(studio)
	request.studio = studio
	YogaClass.sync_all_weekly_occurrences(upcoming_limit=2)
	yoga_class = get_object_or_404(YogaClass, pk=pk, is_published=True, studio=studio)
	form = BookingForm(yoga_class=yoga_class)
	unbooking_form = PublicUnbookingForm()

	if request.method == 'POST':
		action = request.POST.get('action') or 'book'
		if action == 'unbook':
			unbooking_form = PublicUnbookingForm(request.POST)
			if yoga_class.is_past:
				messages.error(
					request,
					'Dette hold er allerede startet, så pladsen kan ikke længere afbookes.'
					if (get_language() or 'en').startswith('da') else
					'This class has already started, so the seat can no longer be released.',
				)
			elif unbooking_form.is_valid():
				phone = unbooking_form.cleaned_data['client_phone']
				booking = yoga_class.bookings.filter(client_phone=phone).order_by('-created_at').first()
				if not booking:
					messages.error(
						request,
						'Vi kunne ikke finde en booking med det telefonnummer på dette hold.'
						if (get_language() or 'en').startswith('da') else
						'We could not find a booking with that phone number for this class.',
					)
				else:
					prebooked_client = yoga_class.prebooked_participant_by_phone(phone)
					if prebooked_client:
						yoga_class.mark_prebooked_client_opted_out(prebooked_client)
					booking.delete()
					messages.success(
						request,
						'Din plads er afbooket for dette hold.'
						if (get_language() or 'en').startswith('da') else
						'Your seat has been released for this class.',
					)
					return redirect('booking:class_detail', studio_slug=studio.slug, pk=yoga_class.pk)
		else:
			with transaction.atomic():
				locked_class = YogaClass.objects.select_for_update().get(pk=yoga_class.pk)
				yoga_class = locked_class
				form = BookingForm(request.POST, yoga_class=locked_class)
				if form.is_valid():
					booking = form.save(commit=False)
					booking.source = Booking.SOURCE_PUBLIC
					booking.save()
					prebooked_client = locked_class.prebooked_participant_by_phone(booking.client_phone)
					if prebooked_client:
						locked_class.clear_prebooked_client_opt_out(prebooked_client)
					is_danish = (get_language() or 'en').startswith('da')
					messages.success(
						request,
						'Din plads er booket. Bekræftelsen er gemt i systemet.'
						if is_danish else
						'Your place is booked. A confirmation is saved in the system.',
					)
					return redirect('booking:class_list', studio_slug=studio.slug)

	context = {
		'yoga_class': yoga_class,
		'form': form,
		'unbooking_form': unbooking_form,
		'studio': studio,
	}
	return render(request, 'booking/class_detail.html', context)
