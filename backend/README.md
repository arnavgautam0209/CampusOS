# CampusOS Backend (Django REST API)

The backend is the **source of truth** for shared campus data. The iOS app's LabOS screens (labs, sign-in, bookings) use it; ESP32 terminals will too.

## Setup

Requires Python 3.9+. macOS's built-in `python3` (3.9) installs Django 4.2. Python 3.10+ installs Django 5.2 LTS, which is recommended because 4.2 is no longer supported.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo --demo-user   # prints the demo user's API token
.venv/bin/python manage.py runserver
```

Then open http://127.0.0.1:8000/api/v1/health/ and http://127.0.0.1:8000/api/v1/labs/.

Admin site: create an account with `.venv/bin/python manage.py createsuperuser`, then visit `/admin/`.

Run tests: `.venv/bin/python manage.py test`

### Reaching it from an iPhone or ESP32
Run `runserver 0.0.0.0:8000` and add your Mac's LAN IP to `DJANGO_ALLOWED_HOSTS` (see `.env.example`). In the app, enter that address in the **Server** field on the sign-in screen (e.g. `192.168.1.20:8000`). The iOS Simulator can use the default `127.0.0.1` directly.

Roles are temporary: superuser = administrator, staff = faculty, everyone else = student.

## API (v1)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/health/` | public | Liveness check |
| POST | `/api/v1/auth/token/` | public | `{username, password}` → `{token}` |
| GET | `/api/v1/auth/me/` | token | Signed-in user `{id, name, email, role}` (same shape as iOS `CampusUser`) |
| GET | `/api/v1/labs/` | public | Labs with equipment (same JSON shape as iOS `Lab`, plus `requiredCertifications`) |
| GET | `/api/v1/labs/{id}/` | public | One lab |
| GET | `/api/v1/bookings/` | token | Your bookings (staff see all) |
| POST | `/api/v1/bookings/` | token | `{labID, start (ISO 8601), durationMinutes}` |
| GET | `/api/v1/bookings/{id}/` | token | One of your bookings |
| POST | `/api/v1/bookings/{id}/cancel/` | token | Cancel an active, unfinished booking |
| POST | `/api/v1/devices/scan/` | device key | Card tap from a reader: classroom attendance (`classroomId`) or lab check-in (`labId`). See [firmware/README.md](../firmware/README.md) for the full contract |
| GET | `/api/v1/attendance/live/` | staff | Open sessions with who's present, readers, and the latest 25 scans (polled by the app) |
| GET | `/api/v1/attendance/mine/` | token | Your attendance records, newest first |
| POST | `/api/v1/attendance/sessions/` | staff | `{classroomId, title}` opens a session (409 if the room already has one) |
| POST | `/api/v1/attendance/sessions/{id}/close/` | staff | Close a session; readers in that room stop marking |
| POST | `/api/v1/ai/planner/` | token | `{prompt}` returns recommended labs, free slots, SkillPass status, missing items and next steps (rate-limited per user) |
| POST | `/api/scan/` | device key (or none in local open-scan mode) | AttendX firmware contract `{card_uid, classroom}` for classroom attendance; see firmware/README.md |
| GET | `/api/v1/inventory/` | public | Equipment with `totalQuantity`, `availableQuantity`, `isLowStock`, `isLoanable`, `underMaintenance` |
| GET | `/api/v1/inventory/loans/` | token | Your loans (`?scope=all` for staff: everything out or reported) |
| POST | `/api/v1/inventory/loans/` | token | `{equipmentId, quantity, days}` borrow: 400 lab-only/maintenance/limits, 403 certification, 404 unknown, 409 not enough stock |
| POST | `/api/v1/inventory/loans/{id}/return/` | token | `{condition: ok|damaged|missing, note}` (borrower or staff) |
| POST | `/api/v1/telemetry/` | device key (sensor in a lab) | `{temperature_c, humidity_pct, gas_raw}` from a SafeLab sensor node; see firmware/README.md |
| GET | `/api/v1/safelab/` | token | Per-lab status (normal/warning/danger/offline), latest reading, last 40 readings, open alerts, thresholds |
| POST | `/api/v1/safelab/alerts/{id}/acknowledge/` | staff | Acknowledge a safety alert |
| GET | `/api/v1/spaces/?date=YYYY-MM-DD` | token | Rooms (kind, capacity, location, features, bookable, free/class now) with busy slots 08:00-20:00 |
| GET/POST | `/api/v1/spaces/bookings/` | token | Your room bookings / `{roomId, start, durationMinutes, attendees, purpose}` (409 overlap, 403 timetabled room, 400 capacity) |
| POST | `/api/v1/spaces/bookings/{id}/cancel/`, `/check-in/` | token | Cancel (booker or staff); check in from 10 min before to 15 min after the start |
| GET | `/api/v1/spaces/utilization/?days=7` | staff | Per-room bookings, booked hours, no-shows, utilization % |
| GET | `/api/v1/certifications/` | public | SkillPass catalogue |
| GET | `/api/v1/certifications/mine/` | token | Your certification records (`status`, `isValid`, `expiresAt`) |
| POST | `/api/v1/certifications/{id}/request/` | token | Ask faculty to certify you (creates a pending record) |
| GET | `/api/v1/certification-records/?status=pending` | staff | Records awaiting a decision |
| POST | `/api/v1/certification-records/{id}/approve/` | staff | Approve (sets expiry from the certification's validity) |
| POST | `/api/v1/certification-records/{id}/revoke/` | staff | Revoke |

Send the token as `Authorization: Token <token>`.

Booking errors: `400` validation (closed lab, past start, duration outside 15–240 min), `401` no token, `403` missing SkillPass certification (body lists `missingCertifications`), `404` unknown lab or someone else's booking, `409` overlaps an active booking in that lab.

## Booking integrity
- The overlap check and insert happen inside one transaction that locks the lab row (`bookings/services.py`).
- A database constraint requires `end > start`.
- Cancelled bookings are kept with `status=cancelled` for history and no longer block the slot.
- **Known limit:** SQLite ignores row locks. Use PostgreSQL before several people share one server.

## SkillPass rules
- A lab can list `required_certifications`. Booking it needs **every** one approved, not revoked, and valid until the session ends. This is checked inside the booking transaction (`skillpass/services.py`).
- Only staff can approve or revoke, never their own record. Each decision records who made it and when. Faculty do this in the app (SkillPass → Requests to Review), through the API, or with the Django admin actions.
- `seed_demo` creates four certifications and makes **Electronics Lab** require *Basic Electronics Safety*. It never grants certifications.
- Equipment requirements are stored and shown in the API but not enforced yet (no equipment checkout exists).
- Demo: as `demo_student`, open Electronics Lab in the app. Booking is refused. Tap **Request Training** (on the lab or the SkillPass screen), approve it in `/admin/` (Skillpass → User certifications → *Approve selected*), pull to refresh SkillPass, and book again.

## Attendance and readers
- Readers authenticate with `Authorization: Device <key>`. Keys are issued with `manage.py device_key <DEVICE_ID>` or the admin action *Generate new key*. They are shown once and only a hash is stored.
- A reader is registered to one classroom. Scans are accepted only while faculty have an **attendance session** open there (from the app's ProxyGuard dashboard or admin → Attendance sessions). Who opened and closed each session is recorded. The database allows one open session per classroom and one record per student per session.
- Card UIDs are registered to students in admin → Campus cards. Every tap, including unknown cards, is logged in admin → Scan events.
- Faculty can add attendance by hand in a session's admin page; those rows are marked `manual`.
- Hardware testing commands: `register_student <roll_number> <card_uid> --name "..."` (username = roll number) and `open_session <classroom> [title]` / `open_session <classroom> --close`.
- `CAMPUSOS_OPEN_SCAN=1` lets `/api/scan/` accept taps without a device key, only while `DJANGO_DEBUG` is on. Before any shared or production use: leave it off, issue every reader a key, use HTTPS, and register readers per classroom.
- Limitation: a UID isn't identity proof, and enrolment isn't checked yet. See firmware/README.md.

## Lab check-in
- A reader belongs to a classroom **or** a lab (database constraint). Lab door readers send `labId`.
- `bookings/services.py` `check_in()` grants access only with the student's own active booking for that lab (from 10 minutes before the start until the end), the lab open, and every required SkillPass certification valid until the booking ends. Otherwise it denies with a reason (`no_booking`, `too_early`, `certification_required`, `lab_closed`).
- The first granted tap stores `checked_in_at` and the reader on the booking (actual usage start); bookings show it as `checkedInAt`, and a checked-in booking can't be cancelled. Every tap, granted or not, is in the scan log with its reason.

## AI Mission Planner
- **Claude only interprets the student's text** (`planner/extraction.py`): it extracts team size, date, time, duration and items. Items can only be matched to real equipment IDs (a JSON schema with an `enum` of catalogue IDs), and the server re-validates everything it returns.
- **Everything else is deterministic** (`planner/engine.py`): labs, equipment availability, capacity, SkillPass status, free slots from real bookings (09:00 to 18:00, 30-minute steps), missing items and next steps. The planner never books or certifies: students act through the normal checked endpoints.
- **Setup:** set `ANTHROPIC_API_KEY` in your environment or `backend/.env`, never in Git. Without it, or if Claude is unreachable, rate-limited or declines, the planner uses keyword matching and the response says so (`engine: "keywords"` plus a note). Set `CAMPUSOS_PLANNER_ENGINE=keywords` to never call Claude. Requests are limited to `CAMPUSOS_PLANNER_RATE` per user (default 30/hour).
- **Model:** Claude Opus 5.5 (`claude-opus-5-5`) at low effort, with structured JSON output and server-side refusal fallback. The student's description is sent to Anthropic's API.

## AssetX inventory
- Equipment has `total_quantity`, `low_stock_threshold` and `is_loanable` (lab-use-only items can't be borrowed); `is_available` off means under maintenance.
- Available units = total minus units on active loans and units returned damaged/missing but not yet resolved. Checkout locks the item row so two students can't take the last unit.
- Borrowing up to 10 units for 1-14 days; equipment certifications (SkillPass) must stay valid until the due date.
- Damaged/missing returns need a note and stay out of stock until staff use the admin action *Mark damaged/missing reports as repaired or replaced*.
- `seed_demo` sets demo stock (e.g. 25 Arduino boards, 8 oscilloscopes that need Basic Electronics Safety).

## SafeLab
- Readings are rated against demo thresholds in `safelab/rules.py` (hobby sensors: not certified limits). Out-of-range kinds open one alert per lab and kind, which escalates but never downgrades, notes when readings return to normal, and stays until faculty acknowledge it.
- A lab shows `offline` when its sensor hasn't reported for 2 minutes; an un-acknowledged alert's level still outranks that.
- `simulate_reading <sensor> --temp --humidity --gas` stores readings marked *simulated*, shown as such in the app.

## SpacePulse rooms
- Rooms are the attendance `Classroom` model, extended with kind (classroom, study room, meeting room), capacity, location, features and `is_bookable`. Students book bookable rooms; staff can book any room (timetabled classrooms).
- `spaces/services.py`: overlap check under a room-row lock (409), capacity, 15-240 min, up to 30 days ahead. A booking not checked in 15 minutes after its start expires and frees the room (no-show).
- Availability shows only *that* a slot is booked to students; staff also see who. A room with an open attendance session shows "Class now".
- Not yet: card-tap check-in for rooms (would change the classroom reader contract), PIR occupancy sensing (PIR detects movement, not verified occupancy).

## Layout
```
config/     settings (env-driven), root URLs, /api/v1/ routing
accounts/   token sign-in and /auth/me/
labs/       Lab + Equipment models, read-only API, seed_demo command
bookings/   Booking model, booking rules (services.py), API
skillpass/  certifications, approval workflow, access checks
attendance/ classrooms, campus cards, attendance sessions and records
devices/    readers, device-key auth, /devices/scan/, scan log, device_key command
inventory/  AssetX stock, loans, returns and damage reports
safelab/    sensor telemetry, safety alerts, simulate_reading command
spaces/     SpacePulse room bookings, check-in, no-shows, utilization
planner/    AI Mission Planner: Claude extraction with keyword fallback, deterministic plan engine
```

## Not yet built
Real roles and permissions, server-side sign-out (token revocation), per-lab safety thresholds, push notifications for alerts, course enrolment checks, the full ProxyGuard verification flow, stock counts in the AI planner (it checks availability, not quantities), PostgreSQL configuration.
