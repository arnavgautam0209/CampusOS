from django.contrib import admin

from .models import Equipment, Lab


class EquipmentInline(admin.TabularInline):
    model = Equipment
    extra = 0


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "location", "capacity", "is_open_for_booking"]
    list_filter = ["is_open_for_booking"]
    filter_horizontal = ["required_certifications"]
    inlines = [EquipmentInline]


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "lab", "is_available"]
    list_filter = ["category", "is_available", "lab"]
    filter_horizontal = ["required_certifications"]
