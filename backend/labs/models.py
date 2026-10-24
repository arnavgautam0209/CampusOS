from django.db import models


class Lab(models.Model):
    # String IDs (e.g. "LAB001") match the iOS app's Lab.id.
    id = models.CharField(primary_key=True, max_length=32)
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=120)
    symbol = models.CharField(max_length=64, help_text="SF Symbol name shown in the iOS app.")
    capacity = models.PositiveIntegerField()
    is_open_for_booking = models.BooleanField(default=True)
    required_certifications = models.ManyToManyField(
        "skillpass.Certification", blank=True, related_name="required_for_labs",
        help_text="Students must hold all of these (approved and unexpired) to book the lab.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.id})"


class Equipment(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="equipment")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60)
    is_available = models.BooleanField(default=True, help_text="Untick while the item is under maintenance.")
    required_certifications = models.ManyToManyField(
        "skillpass.Certification", blank=True, related_name="required_for_equipment",
        help_text="Certifications needed to operate this equipment; enforced when it is borrowed.",
    )
    # AssetX stock. Units available = total minus units on loan or reported damaged/missing.
    total_quantity = models.PositiveIntegerField(default=1)
    low_stock_threshold = models.PositiveIntegerField(
        default=1, help_text="Show as low stock when this many units or fewer are available.")
    is_loanable = models.BooleanField(
        default=False, help_text="Students may borrow it out of the lab (otherwise it's used in the lab only).")

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return f"{self.name} ({self.id})"
