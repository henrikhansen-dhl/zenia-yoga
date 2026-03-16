from datetime import datetime, time, timedelta
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import get_language

from .models import (
    Booking,
    Client,
    Feature,
    SmsReminderLog,
    Studio,
    StudioFeatureAccess,
    StudioInvoice,
    StudioInvoiceLine,
    StudioMembership,
    YogaClass,
)


class LocalizedSplitDateTimeWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = [
            forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            forms.TimeInput(attrs={'type': 'time', 'step': 300}, format='%H:%M'),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            if timezone.is_aware(value):
                value = timezone.localtime(value)
            return [value.date(), value.time().replace(second=0, microsecond=0)]
        return [None, None]


class LocalizedSplitDateTimeField(forms.MultiValueField):
    widget = LocalizedSplitDateTimeWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.DateField(input_formats=['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y']),
            forms.TimeField(input_formats=['%H:%M']),
        )
        super().__init__(fields=fields, require_all_fields=True, *args, **kwargs)

    def compress(self, data_list):
        if not data_list:
            return None

        date_value, time_value = data_list
        if date_value is None or time_value is None:
            return None

        return datetime.combine(date_value, time_value)


class YogaClassForm(forms.ModelForm):
    start_time = LocalizedSplitDateTimeField()
    end_time = LocalizedSplitDateTimeField()

    class Meta:
        model = YogaClass
        fields = [
            'title', 'short_description', 'description',
            'instructor_name', 'start_time', 'end_time',
            'capacity', 'location', 'focus', 'cover_image', 'is_weekly_recurring', 'is_published',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'short_description': forms.TextInput(attrs={'placeholder': 'One-line summary shown on the class card'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        labels = {
            'title': 'Titel' if is_danish else 'Title',
            'short_description': 'Kort beskrivelse' if is_danish else 'Short description',
            'description': 'Beskrivelse' if is_danish else 'Description',
            'instructor_name': 'Underviser' if is_danish else 'Instructor name',
            'start_time': 'Start' if is_danish else 'Start time',
            'end_time': 'Slut' if is_danish else 'End time',
            'capacity': 'Kapacitet' if is_danish else 'Capacity',
            'location': 'Sted' if is_danish else 'Location',
            'focus': 'Fokus' if is_danish else 'Focus',
            'cover_image': 'Billede' if is_danish else 'Cover image',
            'is_weekly_recurring': 'Gentages hver uge' if is_danish else 'Repeats weekly',
            'is_published': 'Synlig på bookingsiden' if is_danish else 'Visible on the booking page',
        }
        placeholders = {
            'title': 'Fx Torsdag aften yoga' if is_danish else 'For example Thursday evening yoga',
            'short_description': 'Kort tekst til bookingkortet' if is_danish else 'One-line summary shown on the class card',
            'description': 'Hvad skal deltagerne vide?' if is_danish else 'What should participants expect?',
            'instructor_name': 'Underviserens navn' if is_danish else 'Instructor name',
            'location': 'Fx yoga-studie i centrum' if is_danish else 'For example downtown yoga studio',
            'focus': 'Fx Restorativ, Vinyasa eller Breathwork' if is_danish else 'For example Restorative, Vinyasa or Breathwork',
        }

        for name, label in labels.items():
            self.fields[name].label = label

        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs['placeholder'] = placeholder

        self.fields['description'].widget.attrs['rows'] = 6

        if self.instance and self.instance.recurrence_parent_id:
            self.fields['is_weekly_recurring'].disabled = True

        for field_name in ('start_time', 'end_time'):
            self.fields[field_name].widget.widgets[0].attrs.update({'lang': language, 'class': 'date-input'})
            self.fields[field_name].widget.widgets[1].attrs.update({'lang': language, 'class': 'time-input'})

        self.fields['capacity'].widget.attrs['min'] = 1
        self.fields['is_weekly_recurring'].help_text = (
            'Systemet opretter automatisk de 2 næste kommende uger for dette hold.'
            if is_danish else
            'The system automatically creates the next 2 upcoming weekly sessions for this class.'
        )
        if self.instance and self.instance.recurrence_parent_id:
            self.fields['is_weekly_recurring'].help_text = (
                'Dette hold er automatisk oprettet fra en ugentlig serie.'
                if is_danish else
                'This class was generated automatically from a weekly series.'
            )
        self.fields['is_published'].help_text = (
            'Holdet vises på den offentlige bookingside.'
            if is_danish else
            'The class appears on the public booking page.'
        )


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['client_name', 'client_email', 'client_phone', 'notes']
        widgets = {
            'client_name': forms.TextInput(attrs={'placeholder': 'Your full name'}),
            'client_email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            'client_phone': forms.TextInput(attrs={'placeholder': 'Optional phone number'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Anything the instructor should know?'}),
        }

    def __init__(self, *args, yoga_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.yoga_class = yoga_class
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        self.fields['client_name'].label = 'Navn' if is_danish else 'Name'
        self.fields['client_email'].label = 'E-mail' if is_danish else 'Email'
        self.fields['client_phone'].label = 'Telefon' if is_danish else 'Phone'
        self.fields['notes'].label = 'Noter' if is_danish else 'Notes'

        self.fields['client_name'].widget.attrs['placeholder'] = (
            'Dit fulde navn' if is_danish else 'Your full name'
        )
        self.fields['client_email'].widget.attrs['placeholder'] = 'you@example.com'
        self.fields['client_phone'].widget.attrs['placeholder'] = (
            'Valgfrit telefonnummer' if is_danish else 'Optional phone number'
        )
        self.fields['notes'].widget.attrs['placeholder'] = (
            'Noget underviseren skal vide?' if is_danish else 'Anything the instructor should know?'
        )

    def clean_client_email(self):
        return self.cleaned_data['client_email'].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('client_email')

        if not self.yoga_class or not email:
            return cleaned_data

        if not self.yoga_class.is_bookable:
            raise forms.ValidationError(
                'Dette hold kan ikke længere bookes.'
                if (get_language() or 'en').startswith('da')
                else 'This class is not available for booking anymore.'
            )

        if self.yoga_class.bookings.filter(client_email__iexact=email).exists():
            self.add_error(
                'client_email',
                'Denne e-mail er allerede booket til holdet.'
                if (get_language() or 'en').startswith('da')
                else 'This email is already booked for the class.',
            )

        return cleaned_data

    def save(self, commit=True):
        booking = super().save(commit=False)
        booking.yoga_class = self.yoga_class
        if commit:
            booking.save()
        return booking


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'reminder_classes']
        widgets = {
            'name': forms.TextInput(),
            'email': forms.EmailInput(),
            'phone': forms.TextInput(),
            'reminder_classes': forms.SelectMultiple(attrs={'size': 6}),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.studio = studio or getattr(self.instance, 'studio', None) or Studio.get_default()
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        self.fields['name'].label = 'Navn' if is_danish else 'Name'
        self.fields['email'].label = 'E-mail' if is_danish else 'Email'
        self.fields['phone'].label = 'Telefon' if is_danish else 'Phone'
        self.fields['reminder_classes'].label = (
            'Kommende hold til påmindelse'
            if is_danish else
            'Upcoming classes for reminder'
        )

        self.fields['name'].widget.attrs['placeholder'] = 'Klientens navn' if is_danish else 'Client name'
        self.fields['email'].widget.attrs['placeholder'] = 'client@example.com'
        self.fields['phone'].widget.attrs['placeholder'] = (
            'Telefonnummer (valgfrit)' if is_danish else 'Phone number (optional)'
        )

        self.fields['reminder_classes'].queryset = YogaClass.objects.filter(
            studio=self.studio,
            is_published=True,
            start_time__gte=timezone.now(),
        ).order_by('start_time')
        self.fields['reminder_classes'].label_from_instance = (
            lambda yoga_class: self._class_choice_label(yoga_class, is_danish)
        )
        self.fields['reminder_classes'].help_text = (
            'Vælg hold som klienten skal have påmindelse om at booke.'
            if is_danish else
            'Choose classes this client should receive reminders to reserve.'
        )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    @staticmethod
    def _class_choice_label(yoga_class, is_danish):
        local_start = timezone.localtime(yoga_class.start_time)
        if is_danish:
            return f"{yoga_class.title} - {local_start:%d-%m-%Y %H:%M}"
        return f"{yoga_class.title} - {local_start:%b %d, %Y %H:%M}"


class WeeklyParticipantsForm(forms.Form):
    participants = forms.ModelMultipleChoiceField(
        queryset=Client.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'size': 8}),
    )

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)
        studio = studio or Studio.get_default()
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        self.fields['participants'].queryset = Client.objects.filter(studio=studio).order_by('name', 'email')
        self.fields['participants'].label = (
            'Deltagere i ugentlig serie'
            if is_danish else
            'Participants in weekly series'
        )
        self.fields['participants'].help_text = (
            'Disse deltagere kan få påmindelse på dagen hvis de endnu ikke har booket plads.'
            if is_danish else
            'These participants can receive day-of reminders if they have not reserved a seat yet.'
        )


class WeeklyParticipantQuickAddForm(forms.Form):
    name = forms.CharField(max_length=120)
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=40, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        self.fields['name'].label = 'Navn' if is_danish else 'Name'
        self.fields['email'].label = 'E-mail' if is_danish else 'Email'
        self.fields['phone'].label = 'Telefon' if is_danish else 'Phone'

        self.fields['name'].widget.attrs['placeholder'] = 'Klientens navn' if is_danish else 'Client name'
        self.fields['email'].widget.attrs['placeholder'] = 'client@example.com'
        self.fields['phone'].widget.attrs['placeholder'] = (
            'Telefonnummer (valgfrit)' if is_danish else 'Phone number (optional)'
        )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class StudioForm(forms.ModelForm):
    enabled_features = forms.ModelMultipleChoiceField(
        queryset=Feature.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'size': 8}),
    )

    class Meta:
        model = Studio
        fields = [
            'name',
            'slug',
            'logo',
            'contact_name',
            'contact_email',
            'contact_phone',
            'billing_email',
            'subscription_notes',
            'is_active',
        ]
        widgets = {
            'subscription_notes': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        self.fields['enabled_features'].queryset = Feature.objects.filter(is_active=True).order_by('name')
        if self.instance.pk:
            self.fields['enabled_features'].initial = self.instance.feature_accesses.filter(
                is_enabled=True,
                feature__is_active=True,
            ).values_list('feature_id', flat=True)

        labels = {
            'name': 'Studienavn' if is_danish else 'Studio name',
            'slug': 'Slug' if is_danish else 'Slug',
            'logo': 'Logo' if is_danish else 'Logo',
            'contact_name': 'Kontaktperson' if is_danish else 'Contact name',
            'contact_email': 'Kontakt e-mail' if is_danish else 'Contact email',
            'contact_phone': 'Kontakttelefon' if is_danish else 'Contact phone',
            'billing_email': 'Faktura e-mail' if is_danish else 'Billing email',
            'subscription_notes': 'Abonnementsnoter' if is_danish else 'Subscription notes',
            'is_active': 'Aktiv' if is_danish else 'Active',
            'enabled_features': 'Aktive funktioner' if is_danish else 'Enabled features',
        }
        placeholders = {
            'name': 'Fx Aarhus Yoga Studio' if is_danish else 'For example Aarhus Yoga Studio',
            'slug': 'fx aarhus-yoga-studio' if is_danish else 'for example aarhus-yoga-studio',
            'contact_name': 'Navn på ejer eller manager' if is_danish else 'Owner or manager name',
            'contact_email': 'studio@example.com',
            'contact_phone': 'Telefonnummer' if is_danish else 'Phone number',
            'billing_email': 'billing@example.com',
            'subscription_notes': (
                'Fx hvilke moduler studiet betaler for, pris og særlige aftaler.'
                if is_danish else
                'For example paid modules, pricing, and agreement notes.'
            ),
        }

        for name, label in labels.items():
            self.fields[name].label = label

        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs['placeholder'] = placeholder

        self.fields['enabled_features'].help_text = (
            'Vælg de funktioner som studiet har adgang til.'
            if is_danish else
            'Choose the functions this studio should have access to.'
        )
        self.fields['logo'].help_text = (
            'Upload et lille logo som vises i instruktørpanelet.'
            if is_danish else
            'Upload a small logo shown in the instructor area.'
        )

    def save(self, commit=True):
        studio = super().save(commit=commit)
        if not commit:
            return studio

        selected_features = set(self.cleaned_data['enabled_features'].values_list('pk', flat=True))
        active_feature_ids = set(Feature.objects.filter(is_active=True).values_list('pk', flat=True))

        for feature_id in selected_features:
            StudioFeatureAccess.objects.update_or_create(
                studio=studio,
                feature_id=feature_id,
                defaults={'is_enabled': True},
            )

        StudioFeatureAccess.objects.filter(
            studio=studio,
            feature_id__in=active_feature_ids - selected_features,
        ).update(is_enabled=False)

        return studio


class FeatureForm(forms.ModelForm):
    class Meta:
        model = Feature
        fields = ['code', 'name', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        labels = {
            'code': 'Funktionskode' if is_danish else 'Feature code',
            'name': 'Navn' if is_danish else 'Name',
            'description': 'Beskrivelse' if is_danish else 'Description',
            'is_active': 'Aktiv' if is_danish else 'Active',
        }
        placeholders = {
            'code': 'fx sms-reminders' if is_danish else 'for example sms-reminders',
            'name': 'Fx SMS påmindelser' if is_danish else 'For example SMS reminders',
            'description': 'Kort beskrivelse af funktionen' if is_danish else 'Short description of the feature',
        }

        for name, label in labels.items():
            self.fields[name].label = label

        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs['placeholder'] = placeholder


class StudioMembershipForm(forms.ModelForm):
    class Meta:
        model = StudioMembership
        fields = ['studio', 'user', 'role', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = get_language() or 'en'
        is_danish = language.startswith('da')
        user_model = get_user_model()

        self.fields['studio'].queryset = Studio.objects.filter(is_active=True).order_by('name')
        self.fields['user'].queryset = user_model.objects.filter(is_active=True).order_by('username')

        labels = {
            'studio': 'Studie' if is_danish else 'Studio',
            'user': 'Bruger' if is_danish else 'User',
            'role': 'Rolle' if is_danish else 'Role',
            'is_active': 'Aktiv' if is_danish else 'Active',
        }
        for name, label in labels.items():
            self.fields[name].label = label

        self.fields['studio'].label_from_instance = lambda studio: studio.name
        self.fields['user'].label_from_instance = self._user_label
        self.fields['role'].help_text = (
            'Brug owner til ejere, manager til studieledere og staff til medarbejdere.'
            if is_danish else
            'Use owner for owners, manager for studio leads, and staff for team members.'
        )

    @staticmethod
    def _user_label(user):
        full_name = user.get_full_name().strip()
        if user.email and full_name:
            return f'{full_name} ({user.email})'
        if user.email:
            return f'{user.username} ({user.email})'
        return user.username


class StudioEmployeeAccessForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField(max_length=254)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    password = forms.CharField(widget=forms.PasswordInput(render_value=False), required=False)
    role = forms.ChoiceField(choices=StudioMembership.ROLE_CHOICES)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, studio=None, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.studio = studio
        self.membership = membership
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        labels = {
            'username': 'Brugernavn' if is_danish else 'Username',
            'email': 'E-mail' if is_danish else 'Email',
            'first_name': 'Fornavn' if is_danish else 'First name',
            'last_name': 'Efternavn' if is_danish else 'Last name',
            'password': 'Kodeord' if is_danish else 'Password',
            'role': 'Rolle' if is_danish else 'Role',
            'is_active': 'Aktiv adgang' if is_danish else 'Active access',
        }
        for field_name, label in labels.items():
            self.fields[field_name].label = label

        self.fields['password'].help_text = (
            'Udfyld kun hvis brugeren er ny eller skal have nyt kodeord.'
            if is_danish else
            'Only fill this in for new users or to set a new password.'
        )

        if membership:
            user = membership.user
            self.initial.update({
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': membership.role,
                'is_active': membership.is_active,
            })

    def clean_username(self):
        return self.cleaned_data['username'].strip()

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        user_model = get_user_model()

        if not username:
            return cleaned_data

        existing_user = user_model.objects.filter(username=username).first()
        if existing_user and self.membership and existing_user.pk == self.membership.user_id:
            return cleaned_data

        if existing_user:
            existing_membership = StudioMembership.objects.filter(
                studio=self.studio,
                user=existing_user,
            ).exclude(pk=getattr(self.membership, 'pk', None)).first()
            if existing_membership:
                raise forms.ValidationError('This user already has access to the selected studio.')

        if not existing_user and not password:
            self.add_error('password', 'Password is required for a new user.')

        return cleaned_data

    def save(self):
        user_model = get_user_model()
        username = self.cleaned_data['username']
        user = user_model.objects.filter(username=username).first()
        created_user = False

        if not user:
            user = user_model(username=username)
            created_user = True

        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_active = True
        user.is_staff = True
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        elif created_user:
            user.set_unusable_password()
        user.save()

        membership = self.membership or StudioMembership(studio=self.studio, user=user)
        membership.role = self.cleaned_data['role']
        membership.is_active = self.cleaned_data['is_active']
        membership.save()
        return membership


class StudioInvoiceCreateForm(forms.Form):
    period_start = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    period_end = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    subscription_fee = forms.DecimalField(max_digits=10, decimal_places=2, initial=Decimal('0.00'))
    employee_fee = forms.DecimalField(max_digits=10, decimal_places=2, initial=Decimal('0.00'))
    sms_fee = forms.DecimalField(max_digits=10, decimal_places=2, initial=Decimal('0.00'))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}))

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.studio = studio
        language = get_language() or 'en'
        is_danish = language.startswith('da')
        if not self.initial.get('period_end'):
            self.initial['period_end'] = timezone.localdate()
        if not self.initial.get('period_start'):
            self.initial['period_start'] = self.initial['period_end'].replace(day=1)

        labels = {
            'period_start': 'Periode start' if is_danish else 'Period start',
            'period_end': 'Periode slut' if is_danish else 'Period end',
            'subscription_fee': 'Pris pr. aktiv service' if is_danish else 'Price per enabled service',
            'employee_fee': 'Pris pr. aktiv medarbejder' if is_danish else 'Price per active employee',
            'sms_fee': 'Pris pr. sendt SMS' if is_danish else 'Price per sent SMS',
            'notes': 'Noter' if is_danish else 'Notes',
        }
        for field_name, label in labels.items():
            self.fields[field_name].label = label

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('period_start')
        end = cleaned_data.get('period_end')
        if start and end and end < start:
            raise forms.ValidationError('The period end must be on or after the period start.')
        return cleaned_data

    def save(self, created_by):
        period_start = self.cleaned_data['period_start']
        period_end = self.cleaned_data['period_end']
        invoice_count = StudioInvoice.objects.filter(studio=self.studio).count() + 1
        invoice_number = f'{self.studio.slug.upper()}-{period_end:%Y%m}-{invoice_count:03d}'
        invoice = StudioInvoice.objects.create(
            studio=self.studio,
            created_by=created_by,
            invoice_number=invoice_number,
            period_start=period_start,
            period_end=period_end,
            notes=self.cleaned_data['notes'],
        )

        enabled_features = list(self.studio.enabled_feature_accesses)
        if enabled_features:
            StudioInvoiceLine.objects.create(
                invoice=invoice,
                description='Enabled services: ' + ', '.join(access.feature.name for access in enabled_features),
                quantity=Decimal(len(enabled_features)),
                unit_price=self.cleaned_data['subscription_fee'],
                sort_order=10,
            )

        active_memberships = self.studio.active_memberships.count()
        if active_memberships:
            StudioInvoiceLine.objects.create(
                invoice=invoice,
                description='Active studio team members',
                quantity=Decimal(active_memberships),
                unit_price=self.cleaned_data['employee_fee'],
                sort_order=20,
            )

        period_start_dt = timezone.make_aware(datetime.combine(period_start, time.min))
        period_end_dt = timezone.make_aware(datetime.combine(period_end + timedelta(days=1), time.min))
        sms_count = SmsReminderLog.objects.filter(
            studio=self.studio,
            status=SmsReminderLog.STATUS_SENT,
            created_at__gte=period_start_dt,
            created_at__lt=period_end_dt,
        ).count()
        if sms_count:
            StudioInvoiceLine.objects.create(
                invoice=invoice,
                description='Sent SMS reminders',
                quantity=Decimal(sms_count),
                unit_price=self.cleaned_data['sms_fee'],
                sort_order=30,
            )

        if not invoice.lines.exists():
            StudioInvoiceLine.objects.create(
                invoice=invoice,
                description='No billable usage found for the selected period',
                quantity=Decimal('1.00'),
                unit_price=Decimal('0.00'),
                sort_order=99,
            )

        return invoice