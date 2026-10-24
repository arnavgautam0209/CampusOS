from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from labs.models import Equipment


class EquipmentLoan(models.Model):
    """Units of one equipment item borrowed by a user. AssetX's record of who has what."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Out on loan"
        RETURNED = "returned", "Returned"
        REPORTED = "reported", "Returned damaged or missing"
        RESOLVED = "resolved", "Repaired or replaced"

    class Condition(models.TextChoices):
        OK = "ok", "OK"
        DAMAGED = "damaged", "Damaged"
        MISSING = "missing", "Missing"

    # Statuses whose units are not on the shelf.
    UNAVAILABLE_STATUSES = (Status.ACTIVE, Status.REPORTED)

    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="loans")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="equipment_loans")
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    checked_out_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    condition = models.CharField(max_length=16, choices=Condition.choices, blank=True)
    note = models.CharField(max_length=300, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-checked_out_at"]
        constraints = [
            models.CheckConstraint(check=Q(quantity__gte=1), name="loan_quantity_at_least_one"),
            models.CheckConstraint(check=Q(due_at__gt=F("checked_out_at")), name="loan_due_after_checkout"),
        ]
        indexes = [models.Index(fields=["equipment", "status"])]

    def __str__(self):
        return f"{self.quantity} × {self.equipment.name} → {self.user} ({self.status})"

    @property
    def is_overdue(self):
        return self.status == self.Status.ACTIVE and self.due_at < timezone.now()
