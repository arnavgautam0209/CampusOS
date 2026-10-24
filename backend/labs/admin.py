from django.contrib import admin

from .models import Equipment, Lab


class EquipmentInline(admin.TabularInline):
    model = Equipment
    extra = 0


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "location", "capacity", "is_open_for_booking", "requires_approval"]
    list_filter = ["is_open_for_booking", "requires_approval"]
    filter_horizontal = ["required_certifications"]
    inlines = [EquipmentInline]


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "lab", "total_quantity", "is_loanable", "is_available"]
    list_filter = ["category", "is_loanable", "is_available", "lab"]
    filter_horizontal = ["required_certifications"]
