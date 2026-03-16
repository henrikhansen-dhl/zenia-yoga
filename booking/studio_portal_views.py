from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language

from .forms import StudioEmployeeAccessForm, StudioInvoiceCreateForm
from .models import SmsReminderLog, StudioInvoice, StudioMembership
from .studio_access import get_user_studio_role, studio_login_required, studio_role_required


def _msg(english, danish):
    return danish if (get_language() or 'en').startswith('da') else english


@studio_login_required
def dashboard(request):
    role = get_user_studio_role(request.user, request.studio)
    memberships = request.studio.active_memberships
    invoices = request.studio.invoices.prefetch_related('lines').all()[:5]
    invoice_total = sum((invoice.subtotal_amount for invoice in invoices), start=0)
    context = {
        'studio': request.studio,
        'studio_role': role,
        'accessible_studio_count': request.available_studios.count(),
        'employee_count': memberships.count(),
        'feature_count': len(request.studio.enabled_feature_codes),
        'invoice_count': request.studio.invoices.count(),
        'invoice_total': invoice_total,
        'recent_invoices': invoices,
    }
    return render(request, 'studio_portal/dashboard.html', context)


@studio_role_required(StudioMembership.ROLE_MANAGER)
def employee_list(request):
    memberships = request.studio.memberships.select_related('user').all().order_by('user__username')
    return render(request, 'studio_portal/employee_list.html', {
        'studio': request.studio,
        'memberships': memberships,
        'membership_count': memberships.count(),
        'active_membership_count': memberships.filter(is_active=True).count(),
    })


@studio_role_required(StudioMembership.ROLE_MANAGER)
def employee_create(request):
    if request.method == 'POST':
        form = StudioEmployeeAccessForm(request.POST, studio=request.studio)
        if form.is_valid():
            membership = form.save()
            messages.success(
                request,
                _msg(
                    f'Access for {membership.user.username} has been created.',
                    f'Adgang for {membership.user.username} er oprettet.',
                ),
            )
            return redirect('studio_portal:employee_list')
    else:
        form = StudioEmployeeAccessForm(studio=request.studio)

    return render(request, 'studio_portal/employee_form.html', {
        'studio': request.studio,
        'form': form,
        'action': _msg('Create employee access', 'Opret medarbejderadgang'),
    })


@studio_role_required(StudioMembership.ROLE_MANAGER)
def employee_edit(request, pk):
    membership = get_object_or_404(StudioMembership.objects.select_related('user', 'studio'), pk=pk, studio=request.studio)
    if request.method == 'POST':
        form = StudioEmployeeAccessForm(request.POST, studio=request.studio, membership=membership)
        if form.is_valid():
            membership = form.save()
            messages.success(
                request,
                _msg(
                    f'Access for {membership.user.username} has been updated.',
                    f'Adgang for {membership.user.username} er opdateret.',
                ),
            )
            return redirect('studio_portal:employee_list')
    else:
        form = StudioEmployeeAccessForm(studio=request.studio, membership=membership)

    return render(request, 'studio_portal/employee_form.html', {
        'studio': request.studio,
        'form': form,
        'membership': membership,
        'action': _msg('Save employee access', 'Gem medarbejderadgang'),
    })


@studio_role_required(StudioMembership.ROLE_MANAGER)
def invoice_list(request):
    invoices = request.studio.invoices.prefetch_related('lines').all()
    sms_this_month = SmsReminderLog.objects.filter(
        studio=request.studio,
        status=SmsReminderLog.STATUS_SENT,
        created_at__year=timezone.now().year,
        created_at__month=timezone.now().month,
    ).count()
    return render(request, 'studio_portal/invoice_list.html', {
        'studio': request.studio,
        'invoices': invoices,
        'invoice_count': invoices.count(),
        'sms_this_month': sms_this_month,
        'employee_count': request.studio.active_memberships.count(),
        'feature_count': len(request.studio.enabled_feature_codes),
    })


@studio_role_required(StudioMembership.ROLE_MANAGER)
def invoice_create(request):
    if request.method == 'POST':
        form = StudioInvoiceCreateForm(request.POST, studio=request.studio)
        if form.is_valid():
            invoice = form.save(created_by=request.user)
            messages.success(
                request,
                _msg(
                    f'Invoice {invoice.invoice_number} has been created.',
                    f'Faktura {invoice.invoice_number} er oprettet.',
                ),
            )
            return redirect('studio_portal:invoice_detail', pk=invoice.pk)
    else:
        form = StudioInvoiceCreateForm(studio=request.studio)

    return render(request, 'studio_portal/invoice_form.html', {
        'studio': request.studio,
        'form': form,
        'action': _msg('Create invoice', 'Opret faktura'),
    })


@studio_role_required(StudioMembership.ROLE_MANAGER)
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        StudioInvoice.objects.select_related('studio', 'created_by').prefetch_related('lines'),
        pk=pk,
        studio=request.studio,
    )
    return render(request, 'studio_portal/invoice_detail.html', {
        'studio': request.studio,
        'invoice': invoice,
    })