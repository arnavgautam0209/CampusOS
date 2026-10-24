# CampusOS

*Your Campus. Connected.* A native iOS / SwiftUI smart-campus app with a Django backend.

## Repository layout
- `ios/` – Xcode project; app source in `ios/CampusOS/` (`Core/` + `Features/`), unit tests in `ios/CampusOSTests/`, screenshot walkthrough in `ios/CampusOSUITests/`
- `scripts/` – `walkthrough.sh` (see below)
- `backend/` – Django REST API (see [backend/README.md](backend/README.md))
- `firmware/` – ESP32 card-reader notes and the scan API contract ([firmware/README.md](firmware/README.md))

## Run the iOS app
1. Install Xcode 16 or newer (the project uses synchronized folders: new files in `ios/CampusOS/` are added to the app automatically).
2. Open `ios/CampusOS.xcodeproj`.
3. Pick an iPhone simulator, then **⌘R** to run and **⌘U** to run the unit tests.

Command line (if `xcode-select` points at Command Line Tools, prefix with `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`):
```bash
xcodebuild test -project ios/CampusOS.xcodeproj -scheme CampusOS -destination 'platform=iOS Simulator,name=iPhone 17' -parallel-testing-enabled NO
```

**LabOS needs the backend running** (next section). Start it, then in the app sign in from the Profile tab (or when you first reserve) with a backend account, e.g. the `demo_student` created by `seed_demo --demo-user`.

## Screenshot walkthrough
`scripts/walkthrough.sh` taps through the real app in the iOS Simulator against the local backend and saves a screenshot of every main screen (plus a screen recording when Xcode provides one) to `walkthrough-output/` (gitignored). It:

1. seeds demo users and data with a one-time password: `demo_ui_*` users, a separate `DEMO-ROOM` with its own `READER-DEMO` reader, demo card UIDs and a booking made through the normal booking rules
2. starts the backend on `127.0.0.1:8000` unless one is already running
3. runs the `WalkthroughUITests` UI test (sign-in, LabOS, SkillPass, Bookings, AI Planner, ProxyGuard as student and faculty)
4. removes the demo data again, even if the run fails

Real rooms, readers, device keys and cards are never touched. Needs the backend virtualenv (next section) and Xcode. Pick a simulator with `SIMULATOR="iPhone 17 Pro" scripts/walkthrough.sh`. The UI test skips itself in normal ⌘U runs.

## Run the backend
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo --demo-user
.venv/bin/python manage.py runserver
```

## Current status
**iOS**
- Home with Campus AI Planner card and six service modules; tabs: Home, Bookings, AI Planner, Profile
- Sign-in with Django token auth; token stored in the Keychain; editable server address
- LabOS (**live backend data**): lab catalogue and equipment from `/api/v1/labs/`; reservations (30 min / 1 h / 2 h) and cancellation through `/api/v1/bookings/`, with loading, error and retry states. Conflicts are checked by the server across all users
- Lab check-in: tapping a card on a lab's door reader checks the student in to their booking; Bookings shows "Tap your card at the lab door" when check-in opens and "Checked in at 10:02 · in use until 11:00" afterwards (refreshes every 5 s while open)
- SkillPass faculty review: staff see **Requests to Review** on the SkillPass screen and approve or decline with one tap (self-approval is refused by the server)
- SkillPass (**live backend data**): your certifications with status and expiry, available training with a **Request Training** / **Request Renewal** button; lab details list required certifications with your standing, and equipment shows its own requirements
- ProxyGuard (**live backend data**): faculty open and close sessions, and see who's present, a live feed of reader taps (new taps highlighted) and reader status. Students see their own attendance. Both refresh every 3 s while open
- AssetX (**live backend data**): equipment by lab with available/total units, low-stock, lab-use-only and maintenance badges; borrow with quantity and loan length, return as OK/damaged/missing; faculty see everything out on loan and damage reports
- SafeLab (**live sensor data**): per-lab status, temperature/humidity/gas tiles, trend charts with warning and danger lines, open alerts that faculty acknowledge, offline and simulated labels; refreshes every 5 s
- SpacePulse is a placeholder
- AI Mission Planner (**live**): describe a project and get recommended labs, free time slots you can book in one tap, SkillPass requirements with Request Training buttons, missing items and next steps. Claude interprets the text; every fact comes from CampusOS data. Without an API key it falls back to keyword matching
- Unit tests for `BookingStore`, `SkillPassStore`, `AttendanceStore`, `PlannerStore`, `APIClient`, sign-in, server address parsing, date parsing and Keychain storage

**Backend**
- `/api/v1/` health, token auth + `/auth/me/`, labs (read-only), bookings (create/list/cancel) with server-side conflict checks and tests
- SafeLab: ESP32 sensor nodes POST DHT22/MQ-2 readings to `/api/v1/telemetry/`; alerts open on demo thresholds and stay until faculty acknowledge
- AI planner: `/api/v1/ai/planner/` (Claude Opus 5.5 extraction + deterministic matching; set `ANTHROPIC_API_KEY` to enable Claude)
- SkillPass: certifications with faculty approval, expiry and revocation; restricted labs refuse bookings (403) without the required certification
- Lab check-in: lab door readers validate the student's booking and SkillPass certifications, answer granted/denied, and record the actual session start
- Attendance: ESP32 readers POST card taps to `/api/v1/devices/scan/` with a device key. Attendance is marked only while faculty have a session open in that room, with duplicate protection and a log of every scan

**Not yet built:** real roles, push notifications, the full ProxyGuard verification flow, SpacePulse rooms.

## Ground rules
- The backend is the source of truth. Anything shown from local demo data is labelled as demo data.
- Never commit secrets: use `backend/.env` (gitignored) based on `.env.example`.
- AI suggests plans; it never grants access or permissions.
