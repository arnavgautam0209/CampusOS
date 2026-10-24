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
    """
    Students get a pending request (no stock reserved until an admin approves); staff check out at once.
    Either way the item must be loanable, in stock and allowed by SkillPass right now.
    """
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
        status = EquipmentLoan.Status.ACTIVE if user.is_staff else EquipmentLoan.Status.PENDING
        return EquipmentLoan.objects.create(equipment=equipment, user=user, quantity=quantity, status=status,
                                            requested_days=days, checked_out_at=now, due_at=due)


def _ensure_pending(loan, reviewer):
    if not reviewer.is_staff:
        raise PermissionDenied("Only admins can review equipment requests.")
    if loan.user_id == reviewer.pk:
        raise PermissionDenied("You can't approve your own request.")
    if loan.status != EquipmentLoan.Status.PENDING:
        raise ValidationError({"status": "This request has already been decided."})


def approve_loan(loan, reviewer, note="", now=None):
    """Turns a pending request into a checkout, re-checking stock and SkillPass under a lock."""
    now = now or timezone.now()
    with transaction.atomic():
        equipment = Equipment.objects.select_for_update().get(pk=loan.equipment_id)
        loan = EquipmentLoan.objects.select_for_update().get(pk=loan.pk)
        _ensure_pending(loan, reviewer)
        if not equipment.is_available or not equipment.is_loanable:
            raise ValidationError({"equipmentId": f"{equipment.name} can't be lent right now."})
        due = now + timedelta(days=loan.requested_days)
        missing = missing_certifications(loan.user, equipment.required_certifications.order_by("name"), due)
        if missing:
            raise CertificationRequired(missing, subject=equipment.name)
        available = available_quantity(equipment)
        if loan.quantity > available:
            raise NotEnoughStock(f"Only {available} {equipment.name} available now; "
                                 f"this request needs {loan.quantity}.")
        loan.status = EquipmentLoan.Status.ACTIVE
        loan.checked_out_at, loan.due_at = now, due
        loan.decided_by, loan.decided_at, loan.decision_note = reviewer, now, (note or "").strip()[:300]
        loan.save(update_fields=["status", "checked_out_at", "due_at", "decided_by", "decided_at", "decision_note"])
        return loan


def reject_loan(loan, reviewer, note="", now=None):
    """Rejected requests never held stock, so nothing is released."""
    with transaction.atomic():
        loan = EquipmentLoan.objects.select_for_update().get(pk=loan.pk)
        _ensure_pending(loan, reviewer)
        loan.status = EquipmentLoan.Status.REJECTED
        loan.decided_by, loan.decided_at = reviewer, now or timezone.now()
        loan.decision_note = (note or "").strip()[:300]
        loan.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
        return loan


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
