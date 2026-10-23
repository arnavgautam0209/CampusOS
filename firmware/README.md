# CampusOS Firmware (ESP32 + RFID reader)

The reader sends each card tap to the Django backend, which decides whether attendance is marked.
The ESP32 never decides by itself; it only shows the server's answer (LEDs, buzzer, OLED, serial).

Hardware used so far: ESP32-S3 + RC522 (13.56 MHz). PN532 works the same way: only the UID matters.

## Scan API contract

```
POST http://<MAC_WIFI_IP>:8000/api/v1/devices/scan/
Content-Type: application/json
Authorization: Device <DEVICE_KEY>

{"uid": "04A1B2C3", "classroomId": "ROOM-101"}
```

- `uid`: the card UID bytes as **uppercase hex, no spaces or colons**: 4 bytes (`04A1B2C3`), 7 bytes (`04A1B2C3D4E5F6`) or 10 bytes. (The server also accepts lowercase or `04:A1:…`, but send the clean form.)
- `classroomId`: the room this reader is registered to (`ROOM-101` in the demo).
- Don't send a time: the server timestamps scans.
- **Always send the `Content-Type: application/json` header.** Without it you get a 400.

### Responses

| HTTP | `result` | Meaning | Suggested feedback |
|---|---|---|---|
| 201 | `marked` | Attendance recorded | Green LED, 1 beep, show `student` |
| 200 | `duplicate` | Already marked in this session | Yellow LED, 2 beeps |
| 404 | `unknown_card` | Card not registered | Red LED, long beep, show `uid` |
| 409 | `no_session` | No attendance session open in this room | Red LED |
| 400 | — | Bad JSON, bad UID, missing header, or reader registered to another room | Print `message` |
| 401 | — | Missing, wrong or disabled device key | Check `secrets.h` |
| timeout | — | Network problem | Retry once, then show error and reconnect Wi-Fi |

Every response has a short `message` to print. Successful scans also include `student`, `session`, `sessionId` and `markedAt`.

Example:
```json
{"result": "marked", "message": "Attendance marked: Alice Rao", "uid": "04A1B2C3",
 "student": "Alice Rao", "sessionId": 1, "session": "CS201 Lecture 5", "markedAt": "2026-10-24T09:01:28+00:00"}
```

### Firmware tips
- Ignore the same UID for ~3 seconds after a scan (a card held on the reader repeats).
- Use an HTTP timeout of ~5 s and check `WiFi.status()` before each POST; reconnect if dropped.
- Keep Wi-Fi credentials and the device key in a `secrets.h` that is **not committed** (add it to `.gitignore`).

## Lab door readers (check-in)

A reader can instead be registered to a **lab** (admin → Devices → set *Lab*, leave *Classroom* empty).
It uses the same endpoint and key header, but sends `labId`:

```json
{"uid": "04A1B2C3", "labId": "LAB001"}
```

The server checks that the card's student has **their own active booking for this lab right now**
(check-in opens 10 minutes before the start) and every **SkillPass certification** the lab needs, valid until
the booking ends. The first granted tap records the actual session start, which the student then sees on the
booking in the app.

| HTTP | `result` | Meaning | Suggested feedback |
|---|---|---|---|
| 201 | `granted` | Checked in. `message` says until when | Green LED, 1 beep, show `message` |
| 200 | `already_checked_in` | Repeat tap during the same booking | Green LED, 2 beeps |
| 403 | `denied` | Not allowed in. `reason` is `no_booking`, `too_early`, `certification_required` or `lab_closed` | Red LED, long beep, show `message` |
| 404 | `unknown_card` | Card not registered | Red LED |
| 400 / 401 | — | Same as classroom readers (wrong `labId`, bad key, …) | Print `message` |

Example: `{"result": "denied", "reason": "too_early", "message": "Alice Rao: Too early. Check in from 13:50."}`

The demo seed creates `READER-LAB001` for the Robotics Lab door; issue its key with
`manage.py device_key READER-LAB001`. A granted tap is a record and a signal only: this prototype must not
drive real locks or equipment power.

## Setting up a demo (backend side)

On the Mac running Django (`backend/`):

1. `.venv/bin/python manage.py migrate` and `.venv/bin/python manage.py seed_demo`
   (creates classroom `ROOM-101` and reader `READER-ROOM-101`).
2. `.venv/bin/python manage.py device_key READER-ROOM-101`: prints the key **once**; put it in `secrets.h`.
   Running it again replaces the key (the old one stops working).
3. Start the server so the ESP32 can reach it, replacing the IP with the Mac's Wi-Fi IP
   (`ipconfig getifaddr en0`):
   ```bash
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,10.21.70.8 .venv/bin/python manage.py runserver 0.0.0.0:8000
   ```
4. In `/admin/` (create an account with `createsuperuser` if needed):
   - **Attendance → Campus cards → Add**: register each card UID to a student user.
     Tip: tap an unregistered card first. The reader gets `unknown_card` with the `uid`, and
     **Devices → Scan events** shows it too.
   - Open a session for `ROOM-101`: in the iOS app as a staff user, **Home → ProxyGuard → Open Session…**
     (or admin → **Attendance → Attendance sessions → Add**). Close it with **Close Session** in the app
     (or the admin *Close selected sessions* action).
5. Tap cards and watch them arrive in the iOS app: **Home → ProxyGuard** signed in as a staff user shows the live
   dashboard; a student sees their own attendance. They also appear in admin under **Attendance sessions** and **Scan events**.

The ESP32 and the Mac must be on the same network. Many event Wi-Fi networks block device-to-device traffic;
if scans never arrive, put both on a phone hotspot.

## Known prototype limitations
- A card UID shows a card was present, not who held it, and UIDs can be cloned. Don't present this as proxy-proof;
  teacher verification is still needed (planned ProxyGuard workflow).
- Plain HTTP on a local network is for the demo only; deployment needs HTTPS.
- Course enrolment isn't checked yet: any registered card can mark attendance in an open session.
