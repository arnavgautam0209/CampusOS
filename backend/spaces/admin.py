from django.contrib import admin

from .models import RoomBooking, Timetable, TimetableEntry, TimetableEvent


@admin.register(RoomBooking)
class RoomBookingAdmin(admin.ModelAdmin):
    list_display = ["room", "user", "start", "end", "attendees", "mode", "status", "checked_in_at"]
    list_filter = ["status", "mode", "room"]
    search_fields = ["user__username", "room__name", "purpose"]
    date_hierarchy = "start"
    readonly_fields = ["id", "created_at", "cancelled_at", "checked_in_at"]


class TimetableEntryInline(admin.TabularInline):
    model = TimetableEntry
    extra = 0
    fields = ["weekday", "start", "end", "room", "activity", "row"]


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    """Activate timetables from the app (it checks conflicts first); the admin is for reading."""
    list_display = ["version", "name", "status", "source_filename", "uploaded_by", "activated_at"]
    list_filter = ["status"]
    readonly_fields = ["version", "status", "uploaded_by", "created_at", "activated_at", "activated_by"]
    inlines = [TimetableEntryInline]


@admin.register(TimetableEvent)
class TimetableEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action", "timetable", "actor", "detail"]
    list_filter = ["action"]
    readonly_fields = ["timetable", "booking", "action", "actor", "detail", "created_at"]
