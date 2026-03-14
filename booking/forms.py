from datetime import datetime

from django import forms
from django.utils import timezone
from django.utils.translation import get_language

from .models import Booking, Client, YogaClass


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
            'location': 'Fx Zenia Yoga Studio' if is_danish else 'For example Zenia Yoga Studio',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = get_language() or 'en'
        is_danish = language.startswith('da')

        self.fields['participants'].queryset = Client.objects.all().order_by('name', 'email')
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