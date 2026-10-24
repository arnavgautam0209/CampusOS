"""
Builds a project plan from extracted requirements using only database facts:
labs, equipment, bookings and SkillPass records. Nothing here comes from the AI
except the requirements themselves, and the plan never grants access: booking
and certification still go through their own checked endpoints.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from bookings.models import Booking
from bookings.services import MAX_DURATION_MINUTES, MIN_DURATION_MINUTES
from labs.models import Lab
from labs.serializers import LabSerializer
from skillpass.models import UserCertification
from skillpass.services import missing_certifications

DAY_START = time(9, 0)
DAY_END = time(18, 0)
SLOT_STEP = timedelta(minutes=30)
SLOTS_PER_LAB = 3
SEARCH_DAYS = 3
MAX_RECOMMENDATIONS = 3
DEFAULT_DURATION = 60

DISCLAIMER = ("CampusOS AI suggests a plan. Lab availability, bookings and certifications are checked "
              "by CampusOS when you act on it, and only faculty can approve training.")


def build_plan(user, extraction, now=None):
    now = now or timezone.now()
    requirements = extraction.requirements
    labs = list(Lab.objects.prefetch_related("equipment", "equipment__required_certifications",
                                             "required_certifications"))
    equipment_by_id = {item.id: (item, lab) for lab in labs for item in lab.equipment.all()}

    duration = _clamp_duration(requirements.duration_minutes)
    day, day_note = _target_day(requirements.date, now)
    requested_ids = {eid for item in requirements.items for eid in item.equipment_ids}

    recommendations = []
    for lab in labs:
        rec = _assess_lab(user, lab, requested_ids, requirements, day, duration, now)
        if rec is not None:
            recommendations.append(rec)
    relevant = [r for r in recommendations if r["_relevance"] > 0]
    fallback_note = None
    if not relevant:
        # Nothing matched: suggest open labs that fit the team rather than nothing.
        relevant = [r for r in recommendations if r["lab"]["isOpenForBooking"] and r["capacityOk"]]
        if relevant:
            fallback_note = "No catalogue equipment matched your description, so these are general-purpose labs."
    relevant.sort(key=lambda r: (-r["_score"], r["lab"]["id"]))
    relevant = relevant[:MAX_RECOMMENDATIONS]
    for rec in relevant:
        del rec["_score"], rec["_relevance"]

    items, missing = _item_report(requirements, equipment_by_id)
    notes = [n for n in (extraction.note and f"AI unavailable, used keyword matching: {extraction.note}",
                         day_note, fallback_note) if n]
    return {
        "engine": extraction.engine,
        "notes": notes,
        "requirements": {
            "summary": requirements.summary,
            "teamSize": requirements.team_size,
            "date": day.isoformat(),
            "startTime": requirements.start_time.strftime("%H:%M") if requirements.start_time else None,
            "durationMinutes": duration,
            "labType": requirements.lab_hint,
            "items": items,
        },
        "recommendations": relevant,
        "missingItems": missing,
        "nextSteps": _next_steps(relevant, missing, requirements, duration),
        "disclaimer": DISCLAIMER,
    }


def _clamp_duration(minutes):
    if not minutes:
        return DEFAULT_DURATION
    rounded = int(round(minutes / 15.0)) * 15
    return max(MIN_DURATION_MINUTES, min(MAX_DURATION_MINUTES, rounded))


def _target_day(requested, now):
    today = timezone.localdate(now)
    if requested is None:
        return today, None
    if requested < today:
        return today, f"{requested:%d %b} has passed, so showing times from today."
    if requested > today + timedelta(days=60):
        return today, "That date is too far ahead to plan, so showing times from today."
    return requested, None


def _assess_lab(user, lab, requested_ids, requirements, day, duration, now):
    lab_equipment = list(lab.equipment.all())
    matched = [e for e in lab_equipment if e.id in requested_ids]
    available = [e for e in matched if e.is_available]
    hint = requirements.lab_hint
    hint_match = bool(hint) and (hint in lab.name.lower()
                                 or any(hint in e.category.lower() for e in lab_equipment))

    team = requirements.team_size
    capacity_ok = team is None or team <= lab.capacity

    slots, slots_day = [], None
    first_slot_end = None
    if lab.is_open_for_booking:
        slots, slots_day = _free_slots(lab, day, duration, requirements.start_time, now)
        first_slot_end = slots[0]["end"] if slots else None

    lab_certs = list(lab.required_certifications.order_by("name"))
    valid_until = first_slot_end or timezone.make_aware(datetime.combine(day, DAY_END))
    missing_lab_certs = {c.id for c in missing_certifications(user, lab_certs, valid_until)}
    records = {r.certification_id: r for r in UserCertification.objects.filter(user=user)}

    certifications = [_cert_entry(c, records, missing_lab_certs, "lab", None) for c in lab_certs]
    seen = {c.id for c in lab_certs}
    for item in matched:
        for cert in item.required_certifications.order_by("name"):
            if cert.id in seen:
                continue
            seen.add(cert.id)
            missing = {c.id for c in missing_certifications(user, [cert], valid_until)}
            certifications.append(_cert_entry(cert, records, missing, "equipment", item.name))

    blockers = []
    if not lab.is_open_for_booking:
        blockers.append("This lab isn't accepting bookings.")
    if not capacity_ok:
        blockers.append(f"Seats {lab.capacity}, but your team has {team}.")
    for cert in certifications:
        if cert["requiredFor"] == "lab" and not cert["isValid"]:
            blockers.append(f"Needs SkillPass certification: {cert['name']}.")
    if lab.is_open_for_booking and not slots:
        blockers.append(f"No free {duration}-minute slots in the next {SEARCH_DAYS} days.")

    relevance = len(matched) * 10 + (3 if hint_match else 0)
    score = (len(available) * 10 + len(matched) * 2 + (4 if hint_match else 0)
             + (5 if lab.is_open_for_booking else -20) + (3 if capacity_ok else -10) - 4 * len(blockers))
    return {
        "lab": LabSerializer(lab).data,
        "matchedEquipment": [{"id": e.id, "name": e.name, "isAvailable": e.is_available} for e in matched],
        "capacityOk": capacity_ok,
        "canBook": not blockers,
        "blockers": blockers,
        "certifications": certifications,
        "slotsDate": slots_day.isoformat() if slots_day else None,
        "suggestedSlots": [{"start": s["start"].isoformat(), "end": s["end"].isoformat()} for s in slots],
        "_relevance": relevance,
        "_score": score,
    }


def _cert_entry(cert, records, missing_ids, required_for, equipment_name):
    record = records.get(cert.id)
    valid = cert.id not in missing_ids
    if valid:
        status = "certified"
    elif record is None:
        status = "not_requested"
    elif record.status == UserCertification.Status.APPROVED:
        status = "expired"
    else:
        status = record.status  # "pending" or "revoked"
    return {"id": cert.id, "name": cert.name, "status": status, "isValid": valid,
            "requiredFor": required_for, "equipment": equipment_name}


def _free_slots(lab, start_day, duration_minutes, preferred_start, now):
    """Up to SLOTS_PER_LAB free slots on the first day (from start_day) that has any."""
    tz = timezone.get_current_timezone()
    duration = timedelta(minutes=duration_minutes)
    for offset in range(SEARCH_DAYS):
        day = start_day + timedelta(days=offset)
        day_start = timezone.make_aware(datetime.combine(day, DAY_START), tz)
        day_end = timezone.make_aware(datetime.combine(day, DAY_END), tz)
        taken = list(Booking.objects.filter(lab=lab, status__in=Booking.HOLDS_SLOT,
                                            start__lt=day_end, end__gt=day_start).values_list("start", "end"))
        free = []
        slot = day_start
        while slot + duration <= day_end:
            end = slot + duration
            if slot > now and not any(start < end and slot < finish for start, finish in taken):
                free.append({"start": slot, "end": end})
            slot += SLOT_STEP
        if free:
            if preferred_start:
                target = timezone.make_aware(datetime.combine(day, preferred_start), tz)
                free.sort(key=lambda s: (abs((s["start"] - target).total_seconds()), s["start"]))
                free = sorted(free[:SLOTS_PER_LAB], key=lambda s: s["start"])
            return free[:SLOTS_PER_LAB], day
    return [], None


def _item_report(requirements, equipment_by_id):
    items, missing = [], []
    for requested in requirements.items:
        matches = []
        for eid in requested.equipment_ids:
            if eid in equipment_by_id:
                equipment, lab = equipment_by_id[eid]
                matches.append({"id": equipment.id, "name": equipment.name, "labId": lab.id,
                                "labName": lab.name, "isAvailable": equipment.is_available})
        if not matches:
            status = "not_in_catalog"
            missing.append({"name": requested.name, "reason": "Not in the campus inventory."})
        elif any(m["isAvailable"] for m in matches):
            status = "available"
        else:
            status = "unavailable"
            missing.append({"name": requested.name, "reason": "In the inventory but currently unavailable."})
        items.append({"name": requested.name, "quantity": requested.quantity, "status": status,
                      "matches": matches})
    return items, missing


def _next_steps(recommendations, missing, requirements, duration):
    steps = []
    if not recommendations:
        return ["No suitable lab found. Try describing the equipment you need, or ask lab staff."]
    best = recommendations[0]
    lab_name = best["lab"]["name"]
    for cert in best["certifications"]:
        if cert["isValid"]:
            continue
        if cert["status"] == "pending":
            steps.append(f"Wait for faculty to approve {cert['name']} (requested).")
        elif cert["requiredFor"] == "lab":
            steps.append(f"Request the {cert['name']} certification in SkillPass; faculty must approve it "
                         f"before you can book {lab_name}.")
        else:
            steps.append(f"Request the {cert['name']} certification before using the {cert['equipment']}.")
    if best["canBook"] and best["suggestedSlots"]:
        first = datetime.fromisoformat(best["suggestedSlots"][0]["start"])
        local = timezone.localtime(first)
        verb = "Request" if best["lab"]["requiresApproval"] else "Reserve"
        note = " Faculty approve requests for this lab." if best["lab"]["requiresApproval"] else ""
        steps.append(f"{verb} {lab_name} on {local:%a %d %b} at {local:%H:%M} for {duration} minutes.{note}")
    elif not best["canBook"]:
        steps.append(f"Resolve the blockers above before booking {lab_name}.")
    for item in missing:
        steps.append(f"Source {item['name']}: {item['reason'].lower()} Ask lab staff or bring your own.")
    if requirements.team_size and not best["capacityOk"]:
        steps.append("Split the team across sessions or ask for a larger room.")
    return steps
