from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Lab
from .serializers import LabSerializer


class LabViewSet(viewsets.ReadOnlyModelViewSet):
    """Public lab catalogue. Changes are made by staff through Django admin."""

    queryset = Lab.objects.prefetch_related("equipment")
    serializer_class = LabSerializer
    permission_classes = [AllowAny]
