from django.contrib import admin, messages
from rest_framework.exceptions import APIException

from . import services
from .models import EquipmentLoan


@admin.register(EquipmentLoan)
class EquipmentLoanAdmin(admin.ModelAdmin):
    list_display = ["equipment", "quantity", "user", "status", "checked_out_at", "due_at", "condition"]
    list_filter = ["status", "condition", "equipment__lab"]
    search_fields = ["user__username", "equipment__name"]
    readonly_fields = ["checked_out_at", "returned_at", "returned_by", "resolved_at", "resolved_by"]
    actions = ["resolve_reports"]

    @admin.action(description="Mark damaged/missing reports as repaired or replaced")
    def resolve_reports(self, request, queryset):
        resolved = 0
        for loan in queryset:
            try:
                services.resolve_report(loan, request.user)
                resolved += 1
            except APIException as error:
                self.message_user(request, f"{loan}: {error.detail}", messages.ERROR)
        self.message_user(request, f"Resolved {resolved} report(s).", messages.SUCCESS)
