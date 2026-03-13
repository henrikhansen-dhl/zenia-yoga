from django import forms

from .models import Booking


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

    def clean_client_email(self):
        return self.cleaned_data['client_email'].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('client_email')

        if not self.yoga_class or not email:
            return cleaned_data

        if not self.yoga_class.is_bookable:
            raise forms.ValidationError('This class is not available for booking anymore.')

        if self.yoga_class.bookings.filter(client_email__iexact=email).exists():
            self.add_error('client_email', 'This email is already booked for the class.')

        return cleaned_data

    def save(self, commit=True):
        booking = super().save(commit=False)
        booking.yoga_class = self.yoga_class
        if commit:
            booking.save()
        return booking