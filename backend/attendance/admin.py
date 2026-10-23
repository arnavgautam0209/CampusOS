from django.contrib import admin, messages
from rest_framework.exceptions import APIException

from . import services
from .models import AttendanceRecord, AttendanceSession, CampusCard, Classroom


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]


@admin.register(CampusCard)
class CampusCardAdmin(admin.ModelAdmin):
    list_display = ["uid", "user", "is_active", "registered_at"]
    list_filter = ["is_active"]
    search_fields = ["uid", "user__username", "user__first_name", "user__last_name"]
    autocomplete_fields = ["user"]


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0
    fields = ["student", "source", "card", "device", "marked_at"]
    readonly_fields = ["card", "device", "marked_at"]
    autocomplete_fields = ["student"]


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "classroom", "opened_by", "opened_at", "closed_at", "present"]
    list_filter = ["classroom", ("closed_at", admin.EmptyFieldListFilter)]
    fields = ["classroom", "title", "opened_by", "opened_at", "closed_by", "closed_at"]
    readonly_fields = ["opened_by", "opened_at", "closed_by", "closed_at"]
    inlines = [AttendanceRecordInline]
    actions = ["close_sessions"]

    @admin.display(description="Present")
    def present(self, session):
        return session.records.count()

    def save_model(self, request, obj, form, change):
        if not change:
            obj.opened_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        # Rows added by hand in the admin are manual attendance, not card scans.
        for record in formset.save(commit=False):
            if record.pk is None:
                record.source = AttendanceRecord.Source.MANUAL
            record.save()
        for record in formset.deleted_objects:
            record.delete()

    @admin.action(description="Close selected sessions")
    def close_sessions(self, request, queryset):
        closed = 0
        for session in queryset.filter(closed_at__isnull=True):
            try:
                services.close_session(session, request.user)
                closed += 1
            except APIException as error:
                self.message_user(request, f"{session}: {error.detail}", messages.ERROR)
        self.message_user(request, f"Closed {closed} session(s).", messages.SUCCESS)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ["student", "session", "source", "card", "device", "marked_at"]
    list_filter = ["source", "session__classroom"]
    search_fields = ["student__username", "card__uid"]
    readonly_fields = ["marked_at"]
