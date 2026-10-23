from django.contrib import admin, messages
from rest_framework.exceptions import APIException

from . import services
from .models import Certification, UserCertification


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "validity_days"]
    search_fields = ["id", "name"]


@admin.register(UserCertification)
class UserCertificationAdmin(admin.ModelAdmin):
    list_display = ["user", "certification", "status", "approved_by", "approved_at", "expires_at"]
    list_filter = ["status", "certification"]
    search_fields = ["user__username", "certification__name"]
    # Approval fields are only set through the actions, so the approver is always recorded.
    readonly_fields = ["status", "requested_at", "approved_by", "approved_at", "expires_at",
                       "revoked_by", "revoked_at"]
    actions = ["approve_selected", "revoke_selected"]

    def _apply(self, request, queryset, action, verb):
        done = 0
        for record in queryset.select_related("certification", "user"):
            try:
                action(record, request.user)
                done += 1
            except APIException as error:
                self.message_user(request, f"{record}: {error.detail}", messages.ERROR)
        if done:
            self.message_user(request, f"{verb} {done} certification(s).", messages.SUCCESS)

    @admin.action(description="Approve selected certifications")
    def approve_selected(self, request, queryset):
        self._apply(request, queryset, services.approve, "Approved")

    @admin.action(description="Revoke selected certifications")
    def revoke_selected(self, request, queryset):
        self._apply(request, queryset, services.revoke, "Revoked")
