from django import forms
from .models import CalendarConfig, UserEventBinding


class CalDAVConfigForm(forms.ModelForm):
    class Meta:
        model = CalendarConfig
        fields = ['caldav_url', 'caldav_username', 'caldav_password']
        widgets = {
            'caldav_password': forms.PasswordInput(),
        }
        help_texts = {
            'caldav_url': "e.g., https://dav.runbox.com/ or http://192.168.1.100:8008/calendars/john.doe/home/"
        }


class UserEventBindingForm(forms.ModelForm):
    class Meta:
        model = UserEventBinding
        fields = ['sheet_name']
        help_texts = {
            'sheet_name': "Enter your name exactly as it appears in the Google Sheet (e.g., 'John Doe')"
        }
