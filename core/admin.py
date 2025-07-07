from django.contrib import admin
from .models import UserProfile, SheetEvent, UserEventBinding, CalendarConfig, UserCalDAVEvent

admin.site.register(UserProfile)
admin.site.register(SheetEvent)
admin.site.register(UserEventBinding)
admin.site.register(CalendarConfig)
admin.site.register(UserCalDAVEvent)
