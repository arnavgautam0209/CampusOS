from django.contrib import admin

from .models import RoomBooking


@admin.register(RoomBooking)
class RoomBookingAdmin(admin.ModelAdmin):
    list_display = ["room", "user", "start", "end", "attendees", "status", "checked_in_at"]
    list_filter = ["status", "room"]
    search_fields = ["user__username", "room__name", "purpose"]
    date_hierarchy = "start"
    readonly_fields = ["id", "created_at", "cancelled_at", "checked_in_at"]
