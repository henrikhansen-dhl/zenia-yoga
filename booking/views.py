from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BookingForm
from .models import YogaClass


def class_list(request):
	classes = YogaClass.objects.filter(
		is_published=True,
		start_time__gte=timezone.now(),
	).order_by('start_time')
	featured_class = classes.first()
	context = {
		'classes': classes,
		'featured_class': featured_class,
	}
	return render(request, 'booking/class_list.html', context)


def class_detail(request, pk):
	yoga_class = get_object_or_404(YogaClass, pk=pk, is_published=True)

	if request.method == 'POST':
		with transaction.atomic():
			locked_class = YogaClass.objects.select_for_update().get(pk=yoga_class.pk)
			yoga_class = locked_class
			form = BookingForm(request.POST, yoga_class=locked_class)
			if form.is_valid():
				form.save()
				messages.success(
					request,
					'Your place is booked. A confirmation is saved in the system.',
				)
				return redirect('booking:class_detail', pk=locked_class.pk)
	else:
		form = BookingForm(yoga_class=yoga_class)

	context = {
		'yoga_class': yoga_class,
		'form': form,
	}
	return render(request, 'booking/class_detail.html', context)
