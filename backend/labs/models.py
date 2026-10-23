from django.db import models


class Lab(models.Model):
    # String IDs (e.g. "LAB001") match the iOS app's Lab.id.
    id = models.CharField(primary_key=True, max_length=32)
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=120)
    symbol = models.CharField(max_length=64, help_text="SF Symbol name shown in the iOS app.")
    capacity = models.PositiveIntegerField()
    is_open_for_booking = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.id})"


class Equipment(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="equipment")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60)
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return f"{self.name} ({self.id})"
