from django.contrib import admin, messages

from .models import Device, ScanEvent


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "classroom", "lab", "is_active", "key_prefix", "key_issued_at", "last_seen_at"]
    list_filter = ["is_active", "classroom", "lab"]
    readonly_fields = ["key_prefix", "key_issued_at", "last_seen_at"]
    actions = ["issue_new_key"]

    @admin.action(description="Generate new key (replaces the old one)")
    def issue_new_key(self, request, queryset):
        for device in queryset:
            key = device.issue_key()
            # Shown once only: just the hash is stored.
            self.message_user(
                request, f"{device.id} key: {key}  (copy it now; it won't be shown again)", messages.WARNING)


@admin.register(ScanEvent)
class ScanEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "device", "uid", "result", "reason", "student", "session", "booking"]
    list_filter = ["result", "device"]
    search_fields = ["uid", "student__username"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
