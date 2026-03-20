import base64
from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from .forms import AuthenticatorSetupForm, AuthenticatorTokenForm
from .two_factor import (
    clear_two_factor_verified,
    get_or_create_user_authenticator_device,
    get_safe_next_url,
    get_user_authenticator_device,
    is_two_factor_verified,
    mark_two_factor_verified,
)


def _msg(english, danish):
    return danish if (get_language() or 'en').startswith('da') else english


def _default_next_url(request):
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    if next_url.startswith('/admin/'):
        return '/admin/'
    return '/studio/'


def _qr_code_data_uri(provisioning_uri):
    qr_code = qrcode.QRCode(border=2, box_size=8)
    qr_code.add_data(provisioning_uri)
    qr_code.make(fit=True)

    image = qr_code.make_image(fill_color='#17322e', back_color='white')
    output = BytesIO()
    image.save(output, format='PNG')
    encoded = base64.b64encode(output.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


@login_required
def setup(request):
    device, _ = get_or_create_user_authenticator_device(request.user)
    next_url = get_safe_next_url(request, fallback=_default_next_url(request))
    can_manage_existing_device = device.is_confirmed and is_two_factor_verified(request)

    if device.is_confirmed and not can_manage_existing_device:
        return redirect('two_factor:verify')

    if request.method == 'POST' and 'regenerate' in request.POST:
        if not can_manage_existing_device:
            raise PermissionDenied('Authenticator reset requires a verified session.')
        device.regenerate_secret()
        device.save(update_fields=['secret_encrypted', 'is_confirmed', 'confirmed_at', 'last_verified_step', 'updated_at'])
        clear_two_factor_verified(request)
        messages.info(
            request,
            _msg(
                'Scan the new QR code and confirm the first code to finish rotating your authenticator.',
                'Scan den nye QR-kode og bekræft den første kode for at færdiggøre udskiftningen af din authenticator.',
            ),
        )
        can_manage_existing_device = False

    needs_secret_save = not device.has_secret
    device.ensure_secret()
    if device._state.adding:
        device.save()
    elif needs_secret_save:
        device.save(update_fields=['secret_encrypted', 'is_confirmed', 'confirmed_at', 'last_verified_step', 'updated_at'])

    provisioning_uri = device.provisioning_uri()

    form = AuthenticatorSetupForm(request.POST or None)
    if request.method == 'POST' and 'regenerate' not in request.POST and form.is_valid():
        if device.verify_token(form.cleaned_data['token']):
            mark_two_factor_verified(request)
            messages.success(
                request,
                _msg(
                    'Authenticator login is now enabled for admin and studio access.',
                    'Authenticator-login er nu aktiveret til admin og studioadgang.',
                ),
            )
            return redirect(next_url)
        form.add_error(
            'token',
            _msg(
                'That code is invalid or has already been used. Try the latest code from your authenticator app.',
                'Koden er ugyldig eller allerede brugt. Prøv den nyeste kode fra din authenticator-app.',
            ),
        )

    context = {
        'form': form,
        'next': next_url,
        'device': device,
        'manual_secret': ' '.join(device.secret[i:i + 4] for i in range(0, len(device.secret), 4)),
        'provisioning_uri': provisioning_uri,
        'qr_code_data_uri': _qr_code_data_uri(provisioning_uri),
        'can_manage_existing_device': can_manage_existing_device,
    }
    return render(request, 'two_factor/setup.html', context)


@login_required
def verify(request):
    device = get_user_authenticator_device(request.user)
    if not device or not device.is_confirmed:
        return redirect('two_factor:setup')

    next_url = get_safe_next_url(request, fallback=_default_next_url(request))
    if is_two_factor_verified(request):
        return redirect(next_url)

    form = AuthenticatorTokenForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if device.verify_token(form.cleaned_data['token'], confirm=False):
            mark_two_factor_verified(request)
            return redirect(next_url)
        form.add_error(
            'token',
            _msg(
                'That code is invalid or has already been used. Wait for the next code and try again.',
                'Koden er ugyldig eller allerede brugt. Vent på næste kode og prøv igen.',
            ),
        )

    return render(request, 'two_factor/verify.html', {
        'form': form,
        'next': next_url,
    })