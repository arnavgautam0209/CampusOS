# CampusOS

*Your Campus. Connected.* A native iOS / SwiftUI smart-campus app with a Django backend.

## Repository layout
- `ios/` – Xcode project; app source in `ios/CampusOS/` (`Core/` + `Features/`), unit tests in `ios/CampusOSTests/`
- `backend/` – Django REST API (see [backend/README.md](backend/README.md))
- `firmware/` – reserved for ESP32 + PN532 firmware

## Run the iOS app
1. Install Xcode 16 or newer (the project uses synchronized folders: new files in `ios/CampusOS/` are added to the app automatically).
2. Open `ios/CampusOS.xcodeproj`.
3. Pick an iPhone simulator, then **⌘R** to run and **⌘U** to run the unit tests.

Command line (if `xcode-select` points at Command Line Tools, prefix with `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`):
```bash
xcodebuild test -project ios/CampusOS.xcodeproj -scheme CampusOS -destination 'platform=iOS Simulator,name=iPhone 17'
```

## Run the backend
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo --demo-user
.venv/bin/python manage.py runserver
```

## Current status
**iOS (demo data, not yet connected to the backend)**
- Home with Campus AI Planner card and six service modules; tabs: Home, Bookings, AI Planner, Profile
- LabOS: lab catalogue, equipment, reservations (30 min / 1 h / 2 h), overlap checking, cancellation. Bookings are saved **on this device only**
- Sample screens for AssetX, SafeLab and SkillPass; placeholders for SpacePulse and ProxyGuard
- AI Planner captures an idea; no AI model is connected
- `BookingStore` unit tests

**Backend**
- `/api/v1/` health, token auth, labs (read-only), bookings (create/list/cancel) with server-side conflict checks and tests

**Not yet built:** iOS ↔ backend integration, roles and SkillPass rules on the server, NFC/ESP32 events, sensor telemetry, attendance, AI planning.

## Ground rules
- The backend is the source of truth. Anything shown from local demo data is labelled as demo data.
- Never commit secrets: use `backend/.env` (gitignored) based on `.env.example`.
- AI suggests plans; it never grants access or permissions.
