from rest_framework.decorators import api_view
from rest_framework.response import Response


def campus_role(user):
    # Temporary mapping until real student/faculty/admin roles exist.
    if user.is_superuser:
        return "administrator"
    if user.is_staff:
        return "faculty"
    return "student"


@api_view(["GET"])
def me(request):
    """The signed-in user, in the shape of the iOS CampusUser struct."""
    user = request.user
    return Response({
        "id": str(user.pk),
        "username": user.get_username(),
        "name": user.get_full_name() or user.get_username(),
        "email": user.email,
        "role": campus_role(user),
    })
