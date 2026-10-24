"""
SafeLab equipment fault reports: students report a fault in one existing piece of lab
equipment; faculty approve, reject (with a reason), mark it under maintenance, or resolve it.
Only physical equipment faults: no free-text equipment and nothing environmental.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from attendance.services import display_name
from labs.models import Equipment, Lab

from .models import EquipmentFault

Status = EquipmentFault.Status
# Which statuses each faculty action may move a report from.
TRANSITIONS = {
    "approve": ({Status.PENDING}, Status.APPROVED),
    "reject": ({Status.PENDING}, Status.REJECTED),
    "maintenance": ({Status.PENDING, Status.APPROVED}, Status.UNDER_MAINTENANCE),
    "resolve": ({Status.APPROVED, Status.UNDER_MAINTENANCE}, Status.RESOLVED),
}


def submit(user, data):
    """data: {labId, equipmentId, category, severity, description}. The equipment must belong to that lab."""
    errors = {}
    lab = Lab.objects.filter(pk=str(data.get("labId") or "")).first()
    if lab is None:
        errors["labId"] = "Choose a laboratory."
    equipment = Equipment.objects.filter(pk=str(data.get("equipmentId") or "")).first()
    if equipment is None:
        errors["equipmentId"] = "Choose an equipment item from the list."
    elif lab is not None and equipment.lab_id != lab.id:
        errors["equipmentId"] = f"{equipment.name} ({equipment.id}) isn't in {lab.name}."
    category = data.get("category")
    if category not in EquipmentFault.Category.values:
        errors["category"] = "Choose a fault category."
    severity = data.get("severity")
    if severity not in EquipmentFault.Severity.values:
        errors["severity"] = "Choose a severity."
    description = str(data.get("description") or "").strip()
    if len(description) < 5:
        errors["description"] = "Describe the fault (at least 5 characters)."
    elif len(description) > 500:
        errors["description"] = "Keep the description under 500 characters."
    if errors:
        raise ValidationError(errors)
    return EquipmentFault.objects.create(equipment=equipment, lab=lab, reporter=user, category=category,
                                         severity=severity, description=description)


@transaction.atomic
def decide(fault, user, action, note=""):
    if not user.is_staff:
        raise PermissionDenied("Only faculty can review equipment reports.")
    if action not in TRANSITIONS:
        raise ValidationError({"action": "Use approve, reject, maintenance or resolve."})
    fault = EquipmentFault.objects.select_for_update().select_related("equipment").get(pk=fault.pk)
    allowed, new_status = TRANSITIONS[action]
    if fault.status not in allowed:
        raise ValidationError({"status": f"A {fault.get_status_display().lower()} report can't be moved to "
                                         f"{new_status.label}."})
    note = (note or "").strip()
    if action == "reject" and not note:
        raise ValidationError({"note": "Give a reason for rejecting the report."})
    fault.status, fault.decided_by = new_status, user
    if note:
        fault.decision_note = note[:300]
    fault.save(update_fields=["status", "decided_by", "decision_note", "updated_at"])
    # Under maintenance takes the item out of use (AssetX shows it); resolving the last open one returns it.
    equipment = fault.equipment
    if new_status == Status.UNDER_MAINTENANCE and equipment.is_available:
        Equipment.objects.filter(pk=equipment.pk).update(is_available=False)
    elif new_status == Status.RESOLVED and not equipment.faults.filter(status=Status.UNDER_MAINTENANCE).exists():
        Equipment.objects.filter(pk=equipment.pk).update(is_available=True)
    return fault


def fault_json(fault):
    return {
        "id": fault.id, "labId": fault.lab_id, "labName": fault.lab.name,
        "equipmentId": fault.equipment_id, "equipmentName": fault.equipment.name,
        "equipmentType": fault.equipment.category,
        "category": fault.category, "categoryLabel": fault.get_category_display(),
        "severity": fault.severity, "description": fault.description, "status": fault.status,
        "reporter": display_name(fault.reporter), "username": fault.reporter.get_username(),
        "decisionNote": fault.decision_note,
        "decidedBy": display_name(fault.decided_by) if fault.decided_by else None,
        "createdAt": fault.created_at.isoformat(), "updatedAt": fault.updated_at.isoformat(),
    }


def analytics(months=6, now=None):
    """Chart data computed from the reports in the database."""
    now = timezone.localtime(now or timezone.now())
    faults = EquipmentFault.objects.all()

    def counted(field, label_field=None, exclude_rejected=True, limit=None):
        rows = (faults.exclude(status=Status.REJECTED) if exclude_rejected else faults).values(
            *([field] + ([label_field] if label_field else []))).annotate(count=Count("id")).order_by("-count", field)
        if limit:
            rows = rows[:limit]
        return [{"key": row[field], "label": row[label_field] if label_field else row[field], "count": row["count"]}
                for row in rows]

    by_status = {row["status"]: row["count"] for row in faults.values("status").annotate(count=Count("id"))}
    # The first day of the month `months - 1` months ago, so the current month is the last bar.
    index = now.year * 12 + now.month - 1 - (months - 1)
    first_month = now.replace(year=index // 12, month=index % 12 + 1, day=1, hour=0, minute=0, second=0,
                              microsecond=0)
    monthly = {row["month"].strftime("%Y-%m"): row["count"]
               for row in faults.filter(created_at__gte=first_month).annotate(month=TruncMonth("created_at"))
               .values("month").annotate(count=Count("id"))}
    month_keys, month = [], first_month
    for _ in range(months):
        month_keys.append(month)
        month = (month + timedelta(days=32)).replace(day=1)
    return {
        "byEquipmentType": counted("equipment__category"),
        "byLab": counted("lab_id", "lab__name"),
        "byStatus": [{"key": s.value, "label": s.label, "count": by_status.get(s.value, 0)} for s in Status],
        "mostReported": counted("equipment_id", "equipment__name", limit=5),
        "monthly": [{"key": m.strftime("%Y-%m"), "label": m.strftime("%b"), "count": monthly.get(m.strftime("%Y-%m"), 0)}
                    for m in month_keys],
        "total": faults.count(),
    }
