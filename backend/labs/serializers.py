from rest_framework import serializers

from .models import Equipment, Lab


# Field names are camelCase so the iOS Codable structs decode them directly.
class EquipmentSerializer(serializers.ModelSerializer):
    isAvailable = serializers.BooleanField(source="is_available")

    class Meta:
        model = Equipment
        fields = ["id", "name", "category", "isAvailable"]


class LabSerializer(serializers.ModelSerializer):
    equipment = EquipmentSerializer(many=True, read_only=True)
    isOpenForBooking = serializers.BooleanField(source="is_open_for_booking")

    class Meta:
        model = Lab
        fields = ["id", "name", "location", "symbol", "capacity", "equipment", "isOpenForBooking"]
