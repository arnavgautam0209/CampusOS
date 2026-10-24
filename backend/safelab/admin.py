from django.contrib import admin

from .models import SafetyAlert, SensorReading


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ["recorded_at", "lab", "device", "temperature_c", "humidity_pct", "gas_raw", "level", "source"]
    list_filter = ["level", "source", "lab"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SafetyAlert)
class SafetyAlertAdmin(admin.ModelAdmin):
    list_display = ["opened_at", "lab", "kind", "level", "message", "cleared_at", "acknowledged_at",
                    "acknowledged_by"]
    list_filter = ["level", "kind", "lab", ("acknowledged_at", admin.EmptyFieldListFilter)]
    readonly_fields = ["opened_at", "last_seen_at", "cleared_at", "acknowledged_at", "acknowledged_by"]
