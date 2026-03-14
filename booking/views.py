from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language

from .forms import BookingForm
from .models import Studio, YogaClass


def _public_studio(studio_slug=None):
	if studio_slug:
		return get_object_or_404(Studio, slug=studio_slug, is_active=True)
	return Studio.get_default()


def default_class_list_redirect(request):
	studio = Studio.get_default()
	return redirect('booking:class_list', studio_slug=studio.slug)


def legacy_class_detail_redirect(request, pk):
	yoga_class = get_object_or_404(
		YogaClass.objects.select_related('studio'),
		pk=pk,
		is_published=True,
	)
	return redirect('booking:class_detail', studio_slug=yoga_class.studio.slug, pk=yoga_class.pk)


def class_list(request, studio_slug):
	now = timezone.now()
	studio = _public_studio(studio_slug)
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
	request.studio = studio
	YogaClass.sync_all_weekly_occurrences(upcoming_limit=2)
	yoga_class = get_object_or_404(YogaClass, pk=pk, is_published=True, studio=studio)

	if request.method == 'POST':
		with transaction.atomic():
			locked_class = YogaClass.objects.select_for_update().get(pk=yoga_class.pk)
			yoga_class = locked_class
			form = BookingForm(request.POST, yoga_class=locked_class)
			if form.is_valid():
				form.save()
				is_danish = (get_language() or 'en').startswith('da')
				messages.success(
					request,
					'Din plads er booket. Bekræftelsen er gemt i systemet.'
					if is_danish else
					'Your place is booked. A confirmation is saved in the system.',
				)
				return redirect('booking:class_list', studio_slug=studio.slug)
	else:
		form = BookingForm(yoga_class=yoga_class)

	context = {
		'yoga_class': yoga_class,
		'form': form,
		'studio': studio,
	}
	return render(request, 'booking/class_detail.html', context)
