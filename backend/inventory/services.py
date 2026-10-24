"""
AssetX rules. The server decides whether a checkout is allowed; the app only
shows what these functions answer.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from labs.models import Equipment
from skillpass.services import CertificationRequired, missing_certifications

from .models import EquipmentLoan

MAX_LOAN_DAYS = 14
MAX_UNITS_PER_LOAN = 10


class NotEnoughStock(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "not_enough_stock"


def units_out(equipment_ids=None):
    """{equipment_id: units on loan or reported damaged/missing}."""
    loans = EquipmentLoan.objects.filter(status__in=EquipmentLoan.UNAVAILABLE_STATUSES)
    if equipment_ids is not None:
        loans = loans.filter(equipment_id__in=equipment_ids)
    return {row["equipment_id"]: row["units"]
            for row in loans.values("equipment_id").annotate(units=Sum("quantity"))}


def available_quantity(equipment, out=None):
    if not equipment.is_available:
        return 0
    taken = (out if out is not None else units_out([equipment.id])).get(equipment.id, 0)
    return max(0, equipment.total_quantity - taken)


def _whole_number(value):
    # JSON true/false are ints in Python; don't let them through as 1/0.
    return isinstance(value, int) and not isinstance(value, bool)


def checkout(user, equipment_id, quantity=1, days=1, now=None):
    now = now or timezone.now()
    if not _whole_number(quantity) or not (1 <= quantity <= MAX_UNITS_PER_LOAN):
        raise ValidationError({"quantity": f"Borrow between 1 and {MAX_UNITS_PER_LOAN} units."})
    if not _whole_number(days) or not (1 <= days <= MAX_LOAN_DAYS):
        raise ValidationError({"days": f"Borrow for 1 to {MAX_LOAN_DAYS} days."})
    due = now + timedelta(days=days)

    with transaction.atomic():
        # Locking the item serialises checkouts so two students can't take the last unit.
        equipment = Equipment.objects.select_for_update().filter(pk=equipment_id).first()
        if equipment is None:
            raise NotFound("Equipment not found.")
        if not equipment.is_loanable:
            raise ValidationError({"equipmentId": f"{equipment.name} is used in the lab and can't be borrowed."})
        if not equipment.is_available:
            raise ValidationError({"equipmentId": f"{equipment.name} is under maintenance."})

        missing = missing_certifications(user, equipment.required_certifications.order_by("name"), due)
        if missing:
            raise CertificationRequired(missing, subject=equipment.name)

        available = available_quantity(equipment)
        if quantity > available:
            raise NotEnoughStock(f"Only {available} {equipment.name} available right now.")
        return EquipmentLoan.objects.create(equipment=equipment, user=user, quantity=quantity,
                                            checked_out_at=now, due_at=due)


def return_loan(loan, returned_by, condition=EquipmentLoan.Condition.OK, note=""):
    if loan.status != EquipmentLoan.Status.ACTIVE:
        raise ValidationError({"status": "This loan has already been returned."})
    if loan.user_id != returned_by.pk and not returned_by.is_staff:
        raise PermissionDenied("Only the borrower or staff can return this loan.")
    if condition not in EquipmentLoan.Condition.values:
        raise ValidationError({"condition": "Use ok, damaged or missing."})
    if condition != EquipmentLoan.Condition.OK and not (note or "").strip():
        raise ValidationError({"note": "Say what happened so lab staff can follow up."})
    loan.status = (EquipmentLoan.Status.RETURNED if condition == EquipmentLoan.Condition.OK
                   else EquipmentLoan.Status.REPORTED)
    loan.condition = condition
    loan.note = (note or "").strip()[:300]
    loan.returned_at = timezone.now()
    loan.returned_by = returned_by
    loan.save()
    return loan


def resolve_report(loan, staff):
    """Staff confirm a damaged/missing report was repaired or replaced; units go back on the shelf."""
    if loan.status != EquipmentLoan.Status.REPORTED:
        raise ValidationError({"status": "Only damaged or missing reports can be resolved."})
    loan.status = EquipmentLoan.Status.RESOLVED
    loan.resolved_at = timezone.now()
    loan.resolved_by = staff
    loan.save(update_fields=["status", "resolved_at", "resolved_by"])
    return loan
