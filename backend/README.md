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
- Only staff can approve or revoke, never their own record. Each decision records who made it and when. Use the API or the Django admin actions.
- `seed_demo` creates four certifications and makes **Electronics Lab** require *Basic Electronics Safety*. It never grants certifications.
- Equipment requirements are stored and shown in the API but not enforced yet (no equipment checkout exists).
- Demo: as `demo_student`, booking Electronics Lab is refused. Approve the request in `/admin/` (Skillpass → User certifications → *Approve selected*) and try again.

## Layout
```
config/     settings (env-driven), root URLs, /api/v1/ routing
accounts/   token sign-in and /auth/me/
labs/       Lab + Equipment models, read-only API, seed_demo command
bookings/   Booking model, booking rules (services.py), API
skillpass/  certifications, approval workflow, access checks
```

## Not yet built
Real roles and permissions, server-side sign-out (token revocation), equipment checkout (to enforce equipment certifications), IoT devices and NFC scans, telemetry, attendance, AI planner, PostgreSQL configuration.
