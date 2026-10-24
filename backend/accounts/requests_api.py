"""
One list of student requests across modules: LabOS lab bookings and AssetX equipment loans.
Approving or rejecting still goes through each module's own endpoint and rules:
    POST /api/v1/bookings/{id}/approve/ | /decline/        {note}
    POST /api/v1/inventory/loans/{id}/approve/ | /reject/  {note}
"""

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from attendance.services import display_name
from bookings.models import Booking
from bookings.services import expire_stale_requests
from inventory.models import EquipmentLoan

# Module statuses → one vocabulary for the app.
LAB_STATUS = {Booking.Status.PENDING: "pending", Booking.Status.ACTIVE: "approved",
              Booking.Status.DECLINED: "rejected", Booking.Status.CANCELLED: "cancelled",
              Booking.Status.EXPIRED: "expired"}
LOAN_STATUS = {EquipmentLoan.Status.PENDING: "pending", EquipmentLoan.Status.ACTIVE: "approved",
               EquipmentLoan.Status.REJECTED: "rejected", EquipmentLoan.Status.RETURNED: "returned",
               EquipmentLoan.Status.REPORTED: "returned", EquipmentLoan.Status.RESOLVED: "returned"}


def _lab(booking):
    return {
        "type": "lab_booking", "id": str(booking.id), "status": LAB_STATUS.get(booking.status, booking.status),
        "title": booking.lab.name,
        "detail": f"{timezone.localtime(booking.start):%a %d %b, %H:%M}–{timezone.localtime(booking.end):%H:%M}",
        "purpose": booking.purpose, "requester": display_name(booking.user), "username": booking.user.get_username(),
        "createdAt": booking.created_at.isoformat(),
        "decidedBy": display_name(booking.decided_by) if booking.decided_by else None,
        "decisionNote": booking.decision_note,
    }


def _loan(loan):
    days = f"{loan.requested_days} day{'s' if loan.requested_days != 1 else ''}"
    return {
        "type": "equipment", "id": str(loan.id), "status": LOAN_STATUS.get(loan.status, loan.status),
        "title": f"{loan.equipment.name} ×{loan.quantity}",
        "detail": f"{loan.equipment.lab.name} · {days}", "purpose": "",
        "requester": display_name(loan.user), "username": loan.user.get_username(),
        "createdAt": loan.checked_out_at.isoformat() if loan.status == EquipmentLoan.Status.PENDING
        else (loan.decided_at or loan.checked_out_at).isoformat(),
        "decidedBy": display_name(loan.decided_by) if loan.decided_by else None,
        "decisionNote": loan.decision_note,
    }


@api_view(["GET"])
def requests(request):
    """
    GET /api/v1/requests/  admins: every pending request (oldest first);
                           students: their own requests, newest first (?status=pending to filter).
    """
    expire_stale_requests(timezone.now())
    bookings = Booking.objects.select_related("lab", "user", "decided_by")
    loans = EquipmentLoan.objects.select_related("equipment__lab", "user", "decided_by")
    if request.user.is_staff:
        bookings = bookings.filter(status=Booking.Status.PENDING)
        loans = loans.filter(status=EquipmentLoan.Status.PENDING)
    else:
        bookings = bookings.filter(user=request.user).exclude(status=Booking.Status.ACTIVE, decided_by__isnull=True)
        loans = loans.filter(user=request.user).exclude(status=EquipmentLoan.Status.ACTIVE, decided_by__isnull=True)
    items = [_lab(b) for b in bookings[:200]] + [_loan(l) for l in loans[:200]]
    status = request.query_params.get("status")
    if status:
        items = [item for item in items if item["status"] == status]
    items.sort(key=lambda item: item["createdAt"], reverse=not request.user.is_staff)
    return Response(items)
