from django.contrib.auth.models import AnonymousUser
from rest_framework import authentication, permissions
from rest_framework.exceptions import AuthenticationFailed

from .models import Device, hash_key

KEYWORD = "Device"


class DeviceKeyAuthentication(authentication.BaseAuthentication):
    """`Authorization: Device <key>`. request.auth becomes the Device; there is no user."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode(errors="ignore").split()
        if not header or header[0] != KEYWORD:
            return None
        if len(header) != 2:
            raise AuthenticationFailed("Invalid device key header.")
        device = Device.objects.filter(key_hash=hash_key(header[1])).select_related("classroom").first()
        if device is None or not device.key_hash:
            raise AuthenticationFailed("Unknown device key.")
        if not device.is_active:
            raise AuthenticationFailed("This device has been disabled.")
        return AnonymousUser(), device

    def authenticate_header(self, request):
        # Makes DRF answer 401 (not 403) when the key is missing.
        return KEYWORD


class IsDevice(permissions.BasePermission):
    message = "A valid device key is required."

    def has_permission(self, request, view):
        return isinstance(request.auth, Device)
