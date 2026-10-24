from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from labs.models import Equipment

from . import services
from .models import EquipmentLoan
from .serializers import InventoryItemSerializer, LoanSerializer


class InventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /inventory/ : equipment with live stock (public, like the lab catalogue)."""

    serializer_class = InventoryItemSerializer
    permission_classes = [AllowAny]
    queryset = Equipment.objects.select_related("lab").prefetch_related("required_certifications").order_by(
        "lab_id", "name")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["units_out"] = services.units_out()
        return context


class LoanViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET  /inventory/loans/            your active and recent loans
    GET  /inventory/loans/?scope=all  staff: everything out or reported
    POST /inventory/loans/            {equipmentId, quantity, days}
    POST /inventory/loans/{id}/return/ {condition: ok|damaged|missing, note}
    POST /inventory/loans/{id}/approve/ and /reject/  admin: {note}
    """

    serializer_class = LoanSerializer

    def get_queryset(self):
        loans = EquipmentLoan.objects.select_related("equipment__lab", "user")
        if self.request.user.is_staff and self.request.query_params.get("scope") == "all":
            return loans.filter(status__in=EquipmentLoan.UNAVAILABLE_STATUSES)
        if self.action in ("return_loan", "approve", "reject") and self.request.user.is_staff:
            return loans
        return loans.filter(user=self.request.user)

    def create(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        loan = services.checkout(request.user, str(data.get("equipmentId", "")),
                                 quantity=data.get("quantity", 1), days=data.get("days", 1))
        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="return")
    def return_loan(self, request, pk=None):
        data = request.data if isinstance(request.data, dict) else {}
        loan = services.return_loan(self.get_object(), request.user,
                                    condition=data.get("condition", "ok"), note=data.get("note", ""))
        return Response(LoanSerializer(loan).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        note = request.data.get("note", "") if isinstance(request.data, dict) else ""
        return Response(LoanSerializer(services.approve_loan(self.get_object(), request.user, str(note))).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        note = request.data.get("note", "") if isinstance(request.data, dict) else ""
        return Response(LoanSerializer(services.reject_loan(self.get_object(), request.user, str(note))).data)
