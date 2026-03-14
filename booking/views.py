from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language

from .forms import BookingForm
from .models import YogaClass


def class_list(request):
	now = timezone.now()
	YogaClass.sync_all_weekly_occurrences(upcoming_limit=2, now=now)
	classes = [
		yoga_class
		for yoga_class in YogaClass.objects.filter(
		is_published=True,
		start_time__gte=now,
		).order_by('start_time')
		if yoga_class.should_show_in_public_list(upcoming_limit=2, now=now)
	]
	featured_class = classes[0] if classes else None
	context = {
		'classes': classes,
		'featured_class': featured_class,
	}
	return render(request, 'booking/class_list.html', context)


def class_detail(request, pk):
	YogaClass.sync_all_weekly_occurrences(upcoming_limit=2)
	yoga_class = get_object_or_404(YogaClass, pk=pk, is_published=True)

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
				return redirect('booking:class_list')
	else:
		form = BookingForm(yoga_class=yoga_class)

	context = {
		'yoga_class': yoga_class,
		'form': form,
	}
	return render(request, 'booking/class_detail.html', context)
