# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)


# Duplicate the events from the sheet
class SheetEvent(models.Model):
    event_id_in_sheet = models.CharField(
        max_length=255, unique=True, help_text="A unique identifier for the event in the sheet (e.g., row number, custom ID)")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    person1_name = models.CharField(max_length=255, blank=True, null=True)
    person2_name = models.CharField(max_length=255, blank=True, null=True)
    person3_name = models.CharField(max_length=255, blank=True, null=True)
    person4_name = models.CharField(max_length=255, blank=True, null=True)


# Bind profile to the exact pronunciation in the sheet
class UserEventBinding(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    sheet_name = models.CharField(
        max_length=255, help_text="The name as it appears in the Google Sheet for this user")

    class Meta:
        # A user can only bind one sheet name
        unique_together = ('user_profile', 'sheet_name')


# Bind a user account to CalDAV credentials
class CalendarConfig(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE)

    caldav_url = models.URLField(
        help_text="e.g., https://caldav.example.com/dav/calendars/user/home/"
    )
    caldav_username = models.CharField(max_length=255)
    # Encryption?
    caldav_password = models.CharField(max_length=255)


class UserCalDAVEvent(models.Model):
    """
    Maps a SheetEvent to a specific user's CalDAV event.
    Used to track which events have been synced and their CalDAV UID.
    """
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    sheet_event = models.ForeignKey(SheetEvent, on_delete=models.CASCADE)
    caldav_uid = models.CharField(max_length=255, unique=True,
                                  help_text="The UID of the event in the CalDAV calendar.")
    last_synced = models.DateTimeField(auto_now=True)

    class Meta:
        # A user syncs a sheet event once
        unique_together = ('user_profile', 'sheet_event')
