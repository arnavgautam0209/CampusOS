from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["lab", "user", "start", "end", "status", "decided_by", "checked_in_at", "created_at"]
    list_filter = ["status", "lab"]
    search_fields = ["user__username", "lab__name"]
    date_hierarchy = "start"
    readonly_fields = ["id", "created_at", "cancelled_at", "checked_in_at", "checked_in_device", "decided_by",
                       "decided_at"]
