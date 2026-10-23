from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Certification, UserCertification
from .serializers import CertificationSerializer, UserCertificationSerializer


class CertificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /certifications/               catalogue (public)
    GET  /certifications/mine/          your certification records
    POST /certifications/{id}/request/  ask faculty to certify you
    """

    queryset = Certification.objects.all()
    serializer_class = CertificationSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=False)
    def mine(self, request):
        records = UserCertification.objects.filter(user=request.user).select_related(
            "certification", "approved_by", "user")
        return Response(UserCertificationSerializer(records, many=True).data)

    @action(detail=True, methods=["post"], url_path="request")
    def request_certification(self, request, pk=None):
        record = services.request_certification(request.user, self.get_object())
        return Response(UserCertificationSerializer(record).data, status=status.HTTP_201_CREATED)


class CertificationRecordViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Faculty only.
    GET  /certification-records/?status=pending
    POST /certification-records/{id}/approve/
    POST /certification-records/{id}/revoke/
    """

    serializer_class = UserCertificationSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        records = UserCertification.objects.select_related("certification", "approved_by", "user")
        wanted = self.request.query_params.get("status")
        return records.filter(status=wanted) if wanted else records

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(UserCertificationSerializer(services.approve(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        return Response(UserCertificationSerializer(services.revoke(self.get_object(), request.user)).data)
