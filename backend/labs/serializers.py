from rest_framework import serializers

from .models import Equipment, Lab


# Field names are camelCase so the iOS Codable structs decode them directly.
class EquipmentSerializer(serializers.ModelSerializer):
    isAvailable = serializers.BooleanField(source="is_available")
    requiredCertifications = serializers.PrimaryKeyRelatedField(
        source="required_certifications", many=True, read_only=True)

    class Meta:
        model = Equipment
        fields = ["id", "name", "category", "isAvailable", "requiredCertifications"]


class LabSerializer(serializers.ModelSerializer):
    equipment = EquipmentSerializer(many=True, read_only=True)
    isOpenForBooking = serializers.BooleanField(source="is_open_for_booking")
    requiresApproval = serializers.BooleanField(source="requires_approval")
    requiredCertifications = serializers.PrimaryKeyRelatedField(
        source="required_certifications", many=True, read_only=True)

    class Meta:
        model = Lab
        fields = ["id", "name", "location", "symbol", "capacity", "equipment", "isOpenForBooking",
                  "requiresApproval", "requiredCertifications"]
