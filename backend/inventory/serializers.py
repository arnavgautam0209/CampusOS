from rest_framework import serializers

from attendance.services import display_name

from .models import EquipmentLoan
from .services import available_quantity


# camelCase field names match the iOS Codable structs.
class InventoryItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    labId = serializers.CharField(source="lab_id")
    labName = serializers.CharField(source="lab.name")
    totalQuantity = serializers.IntegerField(source="total_quantity")
    availableQuantity = serializers.SerializerMethodField()
    isLowStock = serializers.SerializerMethodField()
    isLoanable = serializers.BooleanField(source="is_loanable")
    underMaintenance = serializers.SerializerMethodField()
    requiredCertifications = serializers.PrimaryKeyRelatedField(
        source="required_certifications", many=True, read_only=True)

    def get_availableQuantity(self, item):
        return available_quantity(item, self.context["units_out"])

    def get_isLowStock(self, item):
        return item.is_available and self.get_availableQuantity(item) <= item.low_stock_threshold

    def get_underMaintenance(self, item):
        return not item.is_available


class LoanSerializer(serializers.ModelSerializer):
    equipmentId = serializers.CharField(source="equipment_id", read_only=True)
    equipmentName = serializers.CharField(source="equipment.name", read_only=True)
    labName = serializers.CharField(source="equipment.lab.name", read_only=True)
    borrower = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.get_username", read_only=True)
    checkedOutAt = serializers.DateTimeField(source="checked_out_at", read_only=True)
    dueAt = serializers.DateTimeField(source="due_at", read_only=True)
    returnedAt = serializers.DateTimeField(source="returned_at", read_only=True)
    isOverdue = serializers.BooleanField(source="is_overdue", read_only=True)

    class Meta:
        model = EquipmentLoan
        fields = ["id", "equipmentId", "equipmentName", "labName", "quantity", "status", "borrower", "username",
                  "checkedOutAt", "dueAt", "returnedAt", "isOverdue", "condition", "note"]
        read_only_fields = fields

    def get_borrower(self, loan):
        return display_name(loan.user)
