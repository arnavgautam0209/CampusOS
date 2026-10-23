# CampusOS

Native iOS / SwiftUI starter for CampusOS, a modular smart-campus application.

## Run on your Mac

1. Install Xcode 16 or newer (this project uses Xcode synchronized folders).
2. Clone: `git clone https://github.com/arnavgautam0209/CampusOS.git`
3. Open `ios/CampusOS.xcodeproj` in Xcode.
4. Select an iPhone simulator and press **⌘R**.

## Implemented
- Home screen with six service modules
- Four-tab navigation (Home, Bookings, AI Planner, Profile)
- LabOS lab catalog and local demo reservations, including cancellation and overlap checking
- Demo screens for AssetX, SafeLab, SpacePulse, SkillPass and ProxyGuard
- AI project input screen (no live AI API yet)

**Important:** All data is demonstration data. Bookings are device-local; no central backend, NFC terminal, production identity verification, or AI model is connected.

## Architecture
- `ios/CampusOS/` native SwiftUI application, Core and Features subfolders
- `backend/` reserved for Django REST API
- `firmware/` reserved for ESP32 and PN532 firmware

Do not commit credentials or tokens. Real availability and identity permissions must be validated by Django before production use.
