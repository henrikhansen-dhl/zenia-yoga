from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import get_language

from .forms import FeatureForm, StudioForm, StudioMembershipForm
from .models import Feature, Studio, StudioMembership


def _msg(english, danish):
    return danish if (get_language() or 'en').startswith('da') else english

def _with_public_booking_url(request, studio):
    studio.public_booking_path = reverse('booking:class_list', kwargs={'studio_slug': studio.slug})
    studio.public_booking_url = request.build_absolute_uri(studio.public_booking_path)
    return studio


superuser_required = user_passes_test(
    lambda user: user.is_authenticated and user.is_superuser,
    login_url='/admin/login/',
)


@superuser_required
def studio_list(request):
    studios = Studio.objects.prefetch_related('feature_accesses__feature').all()
    for studio in studios:
        _with_public_booking_url(request, studio)
    features = Feature.objects.filter(is_active=True).order_by('name')
    context = {
        'studios': studios,
        'features': features,
        'studio_count': studios.count(),
        'active_studio_count': studios.filter(is_active=True).count(),
        'feature_count': features.count(),
    }
    return render(request, 'platform/studio_list.html', context)


@superuser_required
def studio_create(request):
    if request.method == 'POST':
        form = StudioForm(request.POST, request.FILES)
        if form.is_valid():
            studio = form.save()
            messages.success(
                request,
                _msg(f'Studio "{studio.name}" has been created.', f'Studiet "{studio.name}" er oprettet.'),
            )
            return redirect('platform:studio_edit', pk=studio.pk)
    else:
        form = StudioForm()

    return render(request, 'platform/studio_form.html', {
        'form': form,
        'action': _msg('Create studio', 'Opret studie'),
    })


@superuser_required
def studio_edit(request, pk):
    studio = get_object_or_404(Studio, pk=pk)
    _with_public_booking_url(request, studio)
    if request.method == 'POST':
        form = StudioForm(request.POST, request.FILES, instance=studio)
        if form.is_valid():
            studio = form.save()
            _with_public_booking_url(request, studio)
            messages.success(
                request,
                _msg(f'Studio "{studio.name}" has been updated.', f'Studiet "{studio.name}" er opdateret.'),
            )
            return redirect('platform:studio_list')
    else:
        form = StudioForm(instance=studio)

    return render(request, 'platform/studio_form.html', {
        'form': form,
        'studio': studio,
        'action': _msg('Save changes', 'Gem ændringer'),
    })


@superuser_required
def feature_list(request):
    features = Feature.objects.all().order_by('name')
    context = {
        'features': features,
        'active_feature_count': features.filter(is_active=True).count(),
    }
    return render(request, 'platform/feature_list.html', context)


@superuser_required
def feature_create(request):
    if request.method == 'POST':
        form = FeatureForm(request.POST)
        if form.is_valid():
            feature = form.save()
            messages.success(
                request,
                _msg(f'Feature "{feature.name}" has been created.', f'Funktionen "{feature.name}" er oprettet.'),
            )
            return redirect('platform:feature_list')
    else:
        form = FeatureForm()

    return render(request, 'platform/feature_form.html', {
        'form': form,
        'action': _msg('Create feature', 'Opret funktion'),
    })


@superuser_required
def feature_edit(request, pk):
    feature = get_object_or_404(Feature, pk=pk)
    if request.method == 'POST':
        form = FeatureForm(request.POST, instance=feature)
        if form.is_valid():
            feature = form.save()
            messages.success(
                request,
                _msg(f'Feature "{feature.name}" has been updated.', f'Funktionen "{feature.name}" er opdateret.'),
            )
            return redirect('platform:feature_list')
    else:
        form = FeatureForm(instance=feature)

    return render(request, 'platform/feature_form.html', {
        'form': form,
        'feature': feature,
        'action': _msg('Save changes', 'Gem ændringer'),
    })


@superuser_required
def membership_list(request):
    memberships = StudioMembership.objects.select_related('studio', 'user').all().order_by('studio__name', 'user__username')
    context = {
        'memberships': memberships,
        'membership_count': memberships.count(),
        'active_membership_count': memberships.filter(is_active=True).count(),
    }
    return render(request, 'platform/membership_list.html', context)


@superuser_required
def membership_create(request):
    if request.method == 'POST':
        form = StudioMembershipForm(request.POST)
        if form.is_valid():
            membership = form.save()
            messages.success(
                request,
                _msg(
                    f'Access for {membership.user.username} has been created.',
                    f'Adgang for {membership.user.username} er oprettet.',
                ),
            )
            return redirect('platform:membership_list')
    else:
        form = StudioMembershipForm()

    return render(request, 'platform/membership_form.html', {
        'form': form,
        'action': _msg('Create access', 'Opret adgang'),
    })


@superuser_required
def membership_edit(request, pk):
    membership = get_object_or_404(StudioMembership, pk=pk)
    if request.method == 'POST':
        form = StudioMembershipForm(request.POST, instance=membership)
        if form.is_valid():
            membership = form.save()
            messages.success(
                request,
                _msg(
                    f'Access for {membership.user.username} has been updated.',
                    f'Adgang for {membership.user.username} er opdateret.',
                ),
            )
            return redirect('platform:membership_list')
    else:
        form = StudioMembershipForm(instance=membership)

    return render(request, 'platform/membership_form.html', {
        'form': form,
        'membership': membership,
        'action': _msg('Save changes', 'Gem ændringer'),
    })