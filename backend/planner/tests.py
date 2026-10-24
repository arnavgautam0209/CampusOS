import json
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Booking
from labs.models import Lab
from skillpass.models import Certification, UserCertification

from . import extraction

URL = "/api/v1/ai/planner/"
HACKATHON_PROMPT = ("We are four students building a line-following robot. We need a robotics lab, "
                    "Arduino boards, motors, IR sensors, soldering equipment, and two hours tomorrow.")


def fake_claude_response(payload, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=json.dumps(payload))])


def claude_payload(**overrides):
    payload = {
        "summary": "Four students building a line-following robot.",
        "teamSize": 4,
        "items": [
            {"name": "Arduino boards", "quantity": None, "equipmentIds": ["EQ008"]},
            {"name": "Motors", "quantity": None, "equipmentIds": ["EQ009"]},
            {"name": "IR sensors", "quantity": None, "equipmentIds": []},
            {"name": "Soldering equipment", "quantity": None, "equipmentIds": ["EQ003"]},
        ],
        "labType": "robotics",
        "date": (timezone.localdate() + timedelta(days=1)).isoformat(),
        "startTime": None,
        "durationMinutes": 120,
    }
    payload.update(overrides)
    return payload


class PlannerTestCase(TestCase):
    def setUp(self):
        cache.clear()
        call_command("seed_demo", verbosity=0)
        User = get_user_model()
        self.student = User.objects.create_user("alice", password="unused-test-pw")
        self.faculty = User.objects.create_user("prof", password="unused-test-pw", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.tomorrow = timezone.localdate() + timedelta(days=1)

    def plan(self, prompt=HACKATHON_PROMPT):
        response = self.client.post(URL, {"prompt": prompt}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def local(self, iso):
        return timezone.localtime(datetime.fromisoformat(iso))

    def claude(self, payload=None, stop_reason="end_turn"):
        """Patches the SDK so Claude returns `payload`; yields the mocked create()."""
        create = mock.Mock(return_value=fake_claude_response(payload or claude_payload(), stop_reason))
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        return mock.patch.object(anthropic, "Anthropic", return_value=client), create


@override_settings(PLANNER_ENGINE="auto")
class ClaudePathTests(PlannerTestCase):
    def test_hackathon_scenario_with_claude(self):
        patcher, create = self.claude()
        with patcher:
            body = self.plan()

        self.assertEqual(body["engine"], "claude")
        self.assertEqual(body["notes"], [])
        req = body["requirements"]
        self.assertEqual((req["teamSize"], req["date"], req["durationMinutes"]), (4, self.tomorrow.isoformat(), 120))
        self.assertEqual([i["status"] for i in req["items"]],
                         ["available", "available", "not_in_catalog", "available"])
        self.assertEqual(body["missingItems"], [{"name": "IR sensors", "reason": "Not in the campus inventory."}])

        best = body["recommendations"][0]
        self.assertEqual(best["lab"]["id"], "LAB001")
        self.assertTrue(best["canBook"])
        self.assertEqual({e["id"] for e in best["matchedEquipment"]}, {"EQ003", "EQ008", "EQ009"})
        self.assertEqual(best["slotsDate"], self.tomorrow.isoformat())
        first = self.local(best["suggestedSlots"][0]["start"])
        self.assertEqual((first.date(), first.time()), (self.tomorrow, time(9, 0)))
        self.assertEqual(self.local(best["suggestedSlots"][0]["end"]) - first, timedelta(minutes=120))
        soldering = next(c for c in best["certifications"] if c["id"] == "CERT-SOLDER")
        self.assertEqual((soldering["status"], soldering["requiredFor"], soldering["equipment"]),
                         ("not_requested", "equipment", "Soldering Station"))
        self.assertTrue(any("IR sensors" in step for step in body["nextSteps"]))
        self.assertTrue(any(step.startswith("Request Robotics Lab") and "Faculty approve" in step
                            for step in body["nextSteps"]))

    def test_request_uses_structured_output_and_catalogue_ids(self):
        patcher, create = self.claude()
        with patcher:
            self.plan()
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["output_config"]["effort"], "low")
        schema = kwargs["output_config"]["format"]["schema"]
        id_enum = schema["properties"]["items"]["items"]["properties"]["equipmentIds"]["items"]["enum"]
        self.assertIn("EQ008", id_enum)
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", kwargs["betas"])
        self.assertIn(HACKATHON_PROMPT, kwargs["messages"][0]["content"])
        self.assertIn("Arduino Uno Boards", kwargs["messages"][0]["content"])

    def test_unknown_ids_and_bad_values_from_claude_are_dropped(self):
        payload = claude_payload(teamSize=-3, durationMinutes=99999, date="not-a-date", startTime="25:99",
                                 items=[{"name": "Laser cutter", "quantity": 2, "equipmentIds": ["EQ999"]}])
        patcher, _ = self.claude(payload)
        with patcher:
            body = self.plan()
        req = body["requirements"]
        self.assertIsNone(req["teamSize"])
        self.assertIsNone(req["startTime"])
        self.assertEqual(req["date"], timezone.localdate().isoformat())
        self.assertEqual(req["durationMinutes"], 60)  # nonsense value ignored, default used
        self.assertEqual(req["items"][0]["matches"], [])
        self.assertEqual(body["missingItems"][0]["name"], "Laser cutter")

    def test_long_sessions_are_capped_at_booking_maximum(self):
        patcher, _ = self.claude(claude_payload(durationMinutes=600))
        with patcher:
            self.assertEqual(self.plan()["requirements"]["durationMinutes"], 240)

    def test_refusal_falls_back_to_keywords(self):
        patcher, _ = self.claude(stop_reason="refusal")
        with patcher:
            body = self.plan()
        self.assertEqual(body["engine"], "keywords")
        self.assertIn("declined", body["notes"][0])

    def test_api_errors_fall_back_with_reason(self):
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        errors = [
            (anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None),
             "ANTHROPIC_API_KEY"),
            (anthropic.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None),
             "busy"),
            (anthropic.APIConnectionError(request=request), "reach"),
            (TypeError("Could not resolve authentication method"), "ANTHROPIC_API_KEY"),
        ]
        for error, expected in errors:
            with mock.patch.object(anthropic, "Anthropic", side_effect=error):
                body = self.plan()
            self.assertEqual(body["engine"], "keywords")
            self.assertIn(expected, body["notes"][0])

    @override_settings(PLANNER_ENGINE="keywords")
    def test_keywords_mode_never_calls_claude(self):
        with mock.patch.object(anthropic, "Anthropic") as client:
            body = self.plan()
        client.assert_not_called()
        self.assertEqual(body["engine"], "keywords")
        self.assertEqual(body["notes"], [])


@override_settings(PLANNER_ENGINE="keywords")
class PlanningRulesTests(PlannerTestCase):
    def test_hackathon_scenario_with_keywords(self):
        body = self.plan()
        req = body["requirements"]
        self.assertEqual((req["teamSize"], req["date"], req["durationMinutes"], req["labType"]),
                         (4, self.tomorrow.isoformat(), 120, "robotics"))
        names = {i["name"] for i in req["items"]}
        self.assertEqual(names, {"Arduino Uno Boards", "DC Gear Motors", "Soldering Station"})
        self.assertNotIn("Robotic Arm", names)  # "robotics lab" is a room, not equipment
        self.assertEqual(body["recommendations"][0]["lab"]["id"], "LAB001")

    def test_restricted_lab_is_blocked_until_certified(self):
        prompt = "I need an oscilloscope for one hour tomorrow"
        best = self.plan(prompt)["recommendations"][0]
        self.assertEqual(best["lab"]["id"], "LAB002")
        self.assertFalse(best["canBook"])
        self.assertIn("Basic Electronics Safety", " ".join(best["blockers"]))
        self.assertIn("Request the Basic Electronics Safety certification", " ".join(self.plan(prompt)["nextSteps"]))
        self.assertNotIn("Training training", " ".join(self.plan()["nextSteps"]))

        UserCertification.objects.create(user=self.student, certification_id="CERT-ELEC-BASIC",
                                         status="approved", approved_by=self.faculty)
        best = self.plan(prompt)["recommendations"][0]
        self.assertTrue(best["canBook"])
        self.assertEqual(best["certifications"][0]["status"], "certified")

    def test_pending_certification_is_reported(self):
        UserCertification.objects.create(user=self.student, certification_id="CERT-ELEC-BASIC")
        body = self.plan("oscilloscope tomorrow")
        self.assertEqual(body["recommendations"][0]["certifications"][0]["status"], "pending")
        self.assertIn("Wait for faculty", body["nextSteps"][0])

    def test_slots_avoid_existing_bookings(self):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(self.tomorrow, time(9, 0)), tz)
        Booking.objects.create(user=self.faculty, lab_id="LAB001", start=start, end=start + timedelta(hours=2))
        slots = self.plan()["recommendations"][0]["suggestedSlots"]
        self.assertEqual(self.local(slots[0]["start"]).time(), time(11, 0))

    def test_preferred_start_time_is_respected(self):
        slots = self.plan("soldering station tomorrow at 3pm for 1 hour")["recommendations"][0]["suggestedSlots"]
        starts = [self.local(s["start"]).time() for s in slots]
        self.assertIn(time(15, 0), starts)
        self.assertTrue(all(time(14, 0) <= t <= time(16, 0) for t in starts))

    def test_full_day_moves_to_next_day(self):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(self.tomorrow, time(9, 0)), tz)
        Booking.objects.create(user=self.faculty, lab_id="LAB001", start=start, end=start + timedelta(hours=9))
        best = self.plan()["recommendations"][0]
        self.assertEqual(best["slotsDate"], (self.tomorrow + timedelta(days=1)).isoformat())

    def test_team_too_big_blocks_lab(self):
        best = self.plan("We are 40 students who need the soldering station tomorrow")["recommendations"][0]
        self.assertEqual(best["lab"]["id"], "LAB001")
        self.assertFalse(best["capacityOk"])
        self.assertFalse(best["canBook"])

    def test_closed_lab_is_never_bookable(self):
        body = self.plan("We need the 3D printer tomorrow")
        printing = next(r for r in body["recommendations"] if r["lab"]["id"] == "LAB003")
        self.assertFalse(printing["canBook"])
        self.assertEqual(printing["suggestedSlots"], [])
        self.assertIn("isn't accepting bookings", printing["blockers"][0])

    def test_nothing_matched_suggests_general_labs(self):
        body = self.plan("I want to write a poem about the sea")
        self.assertTrue(body["recommendations"])
        self.assertTrue(all(r["lab"]["isOpenForBooking"] for r in body["recommendations"]))
        self.assertIn("general-purpose", " ".join(body["notes"]))

    def test_past_date_moves_to_today(self):
        patch_extract = mock.patch.object(extraction, "extract_with_keywords",
                                          return_value=extraction.Requirements(summary="x", date=date(2020, 1, 1)))
        with patch_extract:
            body = self.plan("anything")
        self.assertEqual(body["requirements"]["date"], timezone.localdate().isoformat())
        self.assertIn("has passed", " ".join(body["notes"]))

    def test_planning_never_books_or_certifies(self):
        self.plan()
        self.plan("oscilloscope tomorrow")
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(UserCertification.objects.exists())


class PlannerApiTests(PlannerTestCase):
    def test_requires_sign_in(self):
        self.assertEqual(APIClient().post(URL, {"prompt": "x"}, format="json").status_code, 401)

    def test_prompt_validation(self):
        for prompt in ["", "   ", "x" * 2001]:
            self.assertEqual(self.client.post(URL, {"prompt": prompt}, format="json").status_code, 400)

    @override_settings(PLANNER_ENGINE="keywords")
    def test_rate_limited_per_user(self):
        with mock.patch("planner.views.PlannerThrottle.get_rate", return_value="2/hour"):
            codes = [self.client.post(URL, {"prompt": "soldering"}, format="json").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class KeywordExtractionTests(TestCase):
    TODAY = date(2026, 10, 24)  # a Saturday
    CATALOG = [
        {"id": "EQ003", "name": "Soldering Station", "category": "Tools", "lab": "Robotics Lab"},
        {"id": "EQ002", "name": "Robotic Arm", "category": "Robotics", "lab": "Robotics Lab"},
        {"id": "EQ004", "name": "Oscilloscope", "category": "Testing", "lab": "Electronics Lab"},
    ]

    def extract(self, text):
        return extraction.extract_with_keywords(text, self.CATALOG, self.TODAY)

    def test_team_size_words_and_digits(self):
        self.assertEqual(self.extract("we are four students").team_size, 4)
        self.assertEqual(self.extract("3 people").team_size, 3)
        self.assertIsNone(self.extract("a project").team_size)

    def test_durations(self):
        self.assertEqual(self.extract("for two hours").duration_minutes, 120)
        self.assertEqual(self.extract("an hour").duration_minutes, 60)
        self.assertEqual(self.extract("1.5 hours").duration_minutes, 90)
        self.assertEqual(self.extract("45 minutes").duration_minutes, 45)
        self.assertEqual(self.extract("half an hour").duration_minutes, 30)

    def test_dates(self):
        self.assertEqual(self.extract("tomorrow").date, date(2026, 10, 25))
        self.assertEqual(self.extract("day after tomorrow").date, date(2026, 10, 26))
        self.assertEqual(self.extract("on monday").date, date(2026, 10, 26))
        self.assertEqual(self.extract("on saturday").date, date(2026, 10, 31))  # next week, not today
        self.assertIsNone(self.extract("sometime").date)

    def test_times(self):
        self.assertEqual(self.extract("at 3pm").start_time, time(15, 0))
        self.assertEqual(self.extract("at 10:30").start_time, time(10, 30))
        self.assertEqual(self.extract("at 3").start_time, time(15, 0))
        self.assertEqual(self.extract("in the morning").start_time, time(9, 0))

    def test_item_matching_uses_word_stems(self):
        ids = [i.equipment_ids[0] for i in self.extract("some soldering and an oscilloscope").items]
        self.assertEqual(ids, ["EQ003", "EQ004"])
        self.assertEqual(self.extract("book the robotics lab").items, [])
        self.assertEqual([i.equipment_ids for i in self.extract("a robotic arm").items], [["EQ002"]])
