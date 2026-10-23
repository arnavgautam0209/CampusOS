from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from labs.models import Equipment

from . import engine, extraction

MAX_PROMPT_LENGTH = 2000


class PlannerThrottle(UserRateThrottle):
    # Each plan may call Claude, so cap it per user (rate set in settings).
    scope = "planner"


@api_view(["POST"])
@throttle_classes([PlannerThrottle])
def plan(request):
    """
    POST /api/v1/ai/planner/ {"prompt": "We are four students building a line-following robot..."}
    Returns recommended labs, free slots, SkillPass status and missing items, all from the database.
    """
    prompt = str(request.data.get("prompt", "")).strip() if isinstance(request.data, dict) else ""
    if not prompt:
        raise ValidationError({"prompt": "Describe your project, e.g. what you're building and what you need."})
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValidationError({"prompt": f"Keep the description under {MAX_PROMPT_LENGTH} characters."})

    catalog = [
        {"id": e.id, "name": e.name, "category": e.category, "lab": e.lab.name}
        for e in Equipment.objects.select_related("lab").order_by("id")
    ]
    result = extraction.extract(prompt, catalog, timezone.localdate())
    return Response(engine.build_plan(request.user, result))
