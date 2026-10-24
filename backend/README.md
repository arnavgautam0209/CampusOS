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
| GET | `/api/v1/bookings/` | token | Your bookings; staff add `?scope=pending` (requests to review, soonest first) or `?scope=all` |
| POST | `/api/v1/bookings/` | token | `{labID, start (ISO 8601), durationMinutes, purpose?}`; a student booking for a lab with `requiresApproval` comes back `pending` |
| GET | `/api/v1/bookings/{id}/` | token | One of your bookings (staff: any) |
| POST | `/api/v1/bookings/{id}/cancel/` | token | Cancel a confirmed booking or withdraw a pending request |
| POST | `/api/v1/bookings/{id}/approve/`, `/decline/` | staff | `{note?}`; approve re-checks SkillPass; you can't approve your own request |
| POST | `/api/v1/devices/scan/` | device key | Card tap from a reader: classroom attendance (`classroomId`) or lab check-in (`labId`). See [firmware/README.md](../firmware/README.md) for the full contract |
| GET | `/api/v1/attendance/live/` | staff | Open sessions with who's present, readers, and the latest 25 scans (polled by the app) |
| GET | `/api/v1/attendance/mine/` | token | Your attendance records, newest first |
| GET | `/api/v1/attendance/sessions/` | staff | Recent sessions, open and closed, newest first, with `presentCount` (`?classroom=ECE` to filter) |
| POST | `/api/v1/attendance/sessions/` | staff | `{classroomId, title}` opens a session (409 if the room already has one) |
| POST | `/api/v1/attendance/sessions/{id}/close/` | staff | Close a session; readers in that room stop marking |
| GET | `/api/v1/attendance/sessions/{id}/report/` | staff | Session report: session, classroom, faculty, summary (total, present, absent, `attendancePercentage`), `presentStudents`, `absentStudents`, `notEnrolledAttendees`; `session.status` is `final` or `provisional` |
| GET | `/api/v1/attendance/sessions/{id}/report/pdf/` | staff | The same report as an A4 PDF download (`AttendX_<room>_Session_<id>.pdf`) |
| GET | `/api/v1/attendance/sessions/{id}/report/csv/` | staff | The same report as CSV |
| POST | `/api/v1/ai/planner/` | token | `{prompt}` returns recommended labs, free slots, SkillPass status, missing items and next steps (rate-limited per user) |
| POST | `/api/scan/` | device key (or none in local open-scan mode) | AttendX firmware contract `{card_uid, classroom}` for classroom attendance; see firmware/README.md |
| GET | `/api/v1/inventory/` | public | Equipment with `totalQuantity`, `availableQuantity`, `isLowStock`, `isLoanable`, `underMaintenance` |
| GET | `/api/v1/inventory/loans/` | token | Your loans (`?scope=all` for staff: everything out or reported) |
| POST | `/api/v1/inventory/loans/` | token | `{equipmentId, quantity, days}` borrow: 400 lab-only/maintenance/limits, 403 certification, 404 unknown, 409 not enough stock |
| POST | `/api/v1/inventory/loans/{id}/return/` | token | `{condition: ok|damaged|missing, note}` (borrower or staff) |
| POST | `/api/v1/telemetry/` | device key (sensor in a lab) | `{temperature_c, humidity_pct, gas_raw}` from a SafeLab sensor node; see firmware/README.md |
| GET | `/api/v1/safelab/` | token | Per-lab status (normal/warning/danger/offline), latest reading, last 40 readings, open alerts, thresholds |
| POST | `/api/v1/safelab/alerts/{id}/acknowledge/` | staff | Acknowledge a safety alert |
| GET | `/api/v1/requests/` | token | Admins: every pending lab booking and equipment request; students: their own requests with status and decision (`?status=` filters) |
| POST | `/api/v1/inventory/loans/{id}/approve/`, `/reject/` | staff | `{note}`: approve turns a student's equipment request into a checkout (stock and SkillPass re-checked); reject reserves nothing |
| GET | `/api/v1/spaces/?date=YYYY-MM-DD` | token | Rooms (kind, capacity, location, features, bookable, free/class now) with busy slots and timetabled `lectures` 08:00-20:00 |
| GET | `/api/v1/spaces/availability/?date=&start=HH:MM&duration=60&group_size=8&mode=shared` | token | Rooms that fit the group for the whole time, best fit first: `recommended`, `rooms`, `unavailable` (with `reason`), `message`, active `timetable` |
| GET/POST | `/api/v1/spaces/bookings/` (also `bookings/mine/`) | token | Your room bookings / `{roomId, start, durationMinutes, attendees, purpose, mode}`; `mode` is `shared` or `exclusive` (default). 409 no seats/overlap/class, 403 timetabled room, 400 capacity |
| POST | `/api/v1/spaces/bookings/{id}/cancel/`, `/check-in/` | token | Cancel (booker or staff); check in from 10 min before to 15 min after the start |
| GET | `/api/v1/spaces/utilization/?days=7` | staff | Per-room bookings, booked hours, no-shows, utilization % |
| GET | `/api/v1/spaces/timetables/active/` | token | The active timetable with its weekly classes (404 if none) |
| GET | `/api/v1/spaces/timetables/`, `{id}/`, `history/` | staff | Versions, one version with its classes, audit log |
| POST | `/api/v1/spaces/timetables/upload/` | staff | `{name, filename, csv}` or multipart `file`: validated draft with `preview` and `conflicts` (400 lists bad rows) |
| GET | `/api/v1/spaces/timetables/{id}/preview/`, `conflicts/` | staff | Rooms that become occupied/freed vs the active one; upcoming bookings that clash, with a suggested room |
| POST | `/api/v1/spaces/timetables/{id}/resolve/` | staff | `{bookingId, action: reassign\|cancel, roomId?}` for a clashing booking (logged, shown to the student) |
| POST | `/api/v1/spaces/timetables/{id}/activate/` | staff | Replace the active timetable (409 while bookings clash); the old one is archived and can be re-activated |
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
- Faculty approval: labs have `requires_approval` (on by default; switch it off per lab in the admin). A student's booking for such a lab is `pending` and holds the slot so nobody else can take it while faculty decide. Faculty (staff) approve (`active`, "Approved by …") or decline with a reason (`declined`, slot freed). Requests nobody decided become `expired` at their start time. Staff bookings are confirmed straight away. The door reader denies a pending request with `awaiting_approval`.
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
- Hardware testing commands: `register_student <roll_number> <card_uid> --name "..." [--classroom ECE]` (username = roll number; `--classroom` also puts them on that class roster) and `open_session <classroom> [title]` / `open_session <classroom> --close`.
- `CAMPUSOS_OPEN_SCAN=1` lets `/api/scan/` accept taps without a device key, only while `DJANGO_DEBUG` is on. Before any shared or production use: leave it off, issue every reader a key, use HTTPS, and register readers per classroom.
- Limitation: a UID isn't identity proof, and taps aren't refused for students who aren't enrolled (the report lists them separately). See firmware/README.md.

## Session attendance reports
- **Roster:** `ClassroomEnrollment` (admin → Classroom enrollments) holds each class's students and their roll numbers. Owning a card or having attended never enrolls anyone. To remove a student, set **Left at** instead of deleting the row, so past reports keep them.
- **Present** means an attendance record exists for that session (a card tap while it was open, or a row faculty added by hand, shown as "Added by faculty"). Everyone else on the roster is **absent**. Nobody is present by default, records never cross sessions, and a repeat tap never adds a second record.
- **Roster policy:** a session's roster is everyone enrolled in its classroom at any time while it ran (enrolled before it ended, and not left before it opened). A closed session's report is therefore final: later enrollments or departures don't change it, and taps after closing are refused. Reports for open sessions are marked provisional.
- Attendees with a record but no enrollment appear under **Attended but not enrolled** and aren't counted in the totals or percentage. The percentage is present ÷ roster, rounded to one decimal, and is `null` for an empty roster.
- Reports are read-only (`attendance/reports.py`), take two queries however large the class is, and are staff-only even when `CAMPUSOS_OPEN_SCAN` is on. The scan reply's `roll_number` is the roster roll number when the student is enrolled in that classroom, otherwise the username as before.
- **Demo:** `manage.py seed_attendance_demo` creates ECE001–ECE004 (Aarav Sharma, Riya Verma, Kabir Mehta, Ananya Singh) with sample cards `A1B2C3D4`, `B1C2D3E4`, `C1D2E3F4`, `D1E2F3A4`, enrolls them in ECE, and creates a closed session "Embedded Systems Lecture 01" in which only Aarav and Riya tapped (2 of 4, 50%). It's safe to rerun, never changes an existing user or card that doesn't match the demo data, and gives the students no password. It reuses `demo_faculty` (or creates it without a password).

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

## Student requests and admin approval
- A student's lab booking (LabOS) and equipment borrow (AssetX) are created as **pending**. Admins (staff) see both in `GET /api/v1/requests/` and decide each through its module: `bookings/{id}/approve|decline/` and `inventory/loans/{id}/approve|reject/`, with an optional note the student sees.
- A pending lab booking holds its slot, so no one else can double-book it. A pending equipment request reserves nothing: approval re-checks stock and SkillPass under a row lock, so two approvals can't hand out more units than exist (409). Rejected requests never hold anything. Staff bookings and borrows are confirmed at once, and no one can approve their own request.
- Demo accounts: `DEMO_STUDENT_PASSWORD=… DEMO_ADMIN_PASSWORD=… .venv/bin/python manage.py seed_demo_accounts` creates `demo_student` and `demo_admin` (staff + superuser) and the demo labs and equipment. It's safe to rerun. Without the variables, a password is generated and printed once, only when the account is first created; existing passwords are never reset.
- In the app, the **Requests** tab shows **Admin Requests** (Approve / Reject with reason) to admins, and opens automatically after an admin signs in. Students see **My Requests** with each status and decision.

## SpacePulse rooms
- Rooms are the attendance `Classroom` model, extended with kind (classroom, study room, meeting room), capacity, location, features and `is_bookable`. Students book bookable rooms; staff can book any room (timetabled classrooms).
- `spaces/services.py`: overlap check under a room-row lock (409), capacity, 15-240 min, up to 30 days ahead. A booking not checked in 15 minutes after its start expires and frees the room (no-show).
- Availability shows only *that* a slot is booked to students; staff also see who. A room with an open attendance session shows "Class now".
- Not yet: card-tap check-in for rooms (would change the classroom reader contract), PIR occupancy sensing (PIR detects movement, not verified occupancy).

## SpacePulse classrooms, timetables and seats (Demo University Mode)
- `manage.py seed_spacepulse_demo` adds six **fictional** classrooms (ECE-101 30, ECE-102 45, IT-201 60, CSE-301 75, SEM-01 100, HALL-01 150 seats) and loads `demo_data/spacepulse/Timetable_A_Initial.csv` as v1. It's safe to rerun: existing rooms aren't changed, A is loaded once, and it's activated only if no timetable is active, so an uploaded one is never replaced. `Timetable_B_Updated.csv` is for the live upload; the CSV format is in [demo_data/spacepulse/README.md](demo_data/spacepulse/README.md).
- **Timetables** (`spaces/timetables.py`): weekly classes per room. One version is active; activating another archives it (kept for rollback). A class blocks the whole room for everyone. Uploads are all-or-nothing: any bad row (day, time, unknown room, overlap in the same room) rejects the file with line numbers.
- **Conflicts:** activation is refused (409) while an upcoming booking would overlap a class in the new timetable. Faculty move the booking to another room that's free under both timetables (the best fit is suggested) or cancel it. Each decision is logged (`TimetableEvent`) and shown to the student on the booking (`note`). Nothing is changed silently.
- **Seats** (`spaces/capacity.py`): a room's capacity never changes. *Shared* bookings take the group's seats; free seats over a time range = capacity − the busiest moment of overlapping shared bookings (a sweep over start/end times, so 11:15–12:15 is checked against 11:30–12:00 too). A class or an *exclusive* booking makes free seats 0. Cancelled and expired bookings don't count.
- **Recommendation:** rooms with enough free seats for the whole range, sorted by seats left empty after the group sits down (then smaller room). Deterministic; no AI.
- **Concurrency:** each booking takes a lock before reading seats. PostgreSQL locks the room row (`SELECT … FOR UPDATE`). SQLite ignores that, so a no-op `UPDATE` on the room takes SQLite's database-wide write lock first and a second booking waits for the first to commit. This is fine for a demo; use PostgreSQL for many simultaneous users (SQLite allows one writer at a time and waits up to 5 s).
- **Limits:** timetables repeat weekly (no holidays or one-off exams); times are campus local time (`DJANGO_TIME_ZONE`). The 15-minute no-show release also applies to shared bookings.

### Demo script
1. `manage.py migrate && manage.py seed_spacepulse_demo`, then run the server.
2. **Student** (`demo_student`): SpacePulse → **Find Best Room**: group 8, next **Monday 11:00**, 1 h, Shared Study → ECE-101 is recommended ("22 seats would remain available"; IT-201 shows "Timetabled: Python Programming"). **Confirm Booking**.
3. For **8 of 60 → 52**: Monday **14:00**, group 8 → book **IT-201** from Other Rooms That Fit; search again: IT-201 shows 52 of 60 free.
4. **Faculty** (`demo_faculty`): SpacePulse → **Manage Timetables** → **Upload Timetable (CSV)** → `Timetable_B_Updated.csv` (AirDrop it or put it in Files / iCloud Drive; in the Simulator drag the file onto the window first). The review shows ECE-101 and CSE-301 becoming occupied on Monday 11:00, ECE-102 freed on Monday 15:00, and 1 conflict: the student's ECE-101 booking. **Activate** is blocked until you tap **Move to ECE-102** (or Cancel Booking). Then **Activate Timetable**.
5. **Student** again: Find Best Room for Monday 11:00 → ECE-102 is recommended, ECE-101 shows "Timetabled: Microcontrollers"; the booking shows "Moved from ECE-101 to ECE-102 by Demo Faculty…".
6. To reset for another run: in Manage Timetables open **v1 Timetable A** → **Re-activate This Version** (cancel the student's Monday bookings first if they clash).

## Layout
```
config/     settings (env-driven), root URLs, /api/v1/ routing
accounts/   token sign-in and /auth/me/
labs/       Lab + Equipment models, read-only API, seed_demo command
bookings/   Booking model, booking rules (services.py), API
skillpass/  certifications, approval workflow, access checks
attendance/ classrooms, campus cards, enrollments, attendance sessions and records; reports.py builds session reports
devices/    readers, device-key auth, /devices/scan/, scan log, device_key command
inventory/  AssetX stock, loans, returns and damage reports
safelab/    sensor telemetry, safety alerts, simulate_reading command
spaces/     SpacePulse room bookings, shared seats (capacity.py), timetables (timetables.py), check-in, no-shows, utilization
planner/    AI Mission Planner: Claude extraction with keyword fallback, deterministic plan engine
```

## Not yet built
Real roles and permissions, server-side sign-out (token revocation), per-lab safety thresholds, push notifications for alerts, course enrolment checks, the full ProxyGuard verification flow, stock counts in the AI planner (it checks availability, not quantities), PostgreSQL configuration.
