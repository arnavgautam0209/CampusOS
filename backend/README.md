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
| GET | `/api/v1/labs/` | public | Labs with equipment (same JSON shape as iOS `Lab`) |
| GET | `/api/v1/labs/{id}/` | public | One lab |
| GET | `/api/v1/bookings/` | token | Your bookings (staff see all) |
| POST | `/api/v1/bookings/` | token | `{labID, start (ISO 8601), durationMinutes}` |
| GET | `/api/v1/bookings/{id}/` | token | One of your bookings |
| POST | `/api/v1/bookings/{id}/cancel/` | token | Cancel an active, unfinished booking |

Send the token as `Authorization: Token <token>`.

Booking errors: `400` validation (closed lab, past start, duration outside 15–240 min), `401` no token, `404` unknown lab or someone else's booking, `409` overlaps an active booking in that lab.

## Booking integrity
- The overlap check and insert happen inside one transaction that locks the lab row (`bookings/services.py`).
- A database constraint requires `end > start`.
- Cancelled bookings are kept with `status=cancelled` for history and no longer block the slot.
- **Known limit:** SQLite ignores row locks. Use PostgreSQL before several people share one server.

## Layout
```
config/     settings (env-driven), root URLs, /api/v1/ routing
accounts/   token sign-in and /auth/me/
labs/       Lab + Equipment models, read-only API, seed_demo command
bookings/   Booking model, booking rules (services.py), API
```

## Not yet built
Real roles and permissions, server-side sign-out (token revocation), SkillPass certifications, IoT devices and NFC scans, telemetry, attendance, AI planner, PostgreSQL configuration.
