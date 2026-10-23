#!/usr/bin/env bash
# Screenshot walkthrough of the CampusOS iOS app against the local Django backend.
#
#   scripts/walkthrough.sh
#
# 1. Seeds demo users and data (demo_ui_* users, DEMO-ROOM, READER-DEMO) with a
#    one-time password. Real rooms, readers, cards and bookings are not touched.
# 2. Starts the backend on 127.0.0.1:8000 unless one is already running there.
# 3. Runs the WalkthroughUITests UI test in the iOS Simulator.
# 4. Exports the screenshots and screen recording to walkthrough-output/.
# 5. Removes the demo data and stops the backend it started (also on failure).
#
# Options (environment variables):
#   SIMULATOR="iPhone 17"            simulator name to run on
#   OUTPUT="walkthrough-output"      where screenshots go (gitignored)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$REPO/backend"
PYTHON="$BACKEND/.venv/bin/python"
SIMULATOR="${SIMULATOR:-iPhone 17}"
OUTPUT="${OUTPUT:-$REPO/walkthrough-output}"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health/"
SERVER_PID=""

if [[ ! -x "$PYTHON" ]]; then
  echo "Backend virtualenv not found. Set it up first (see backend/README.md)." >&2
  exit 1
fi

# xcodebuild needs full Xcode; use it directly if xcode-select points at Command Line Tools.
if [[ "$(xcode-select -p 2>/dev/null)" == *CommandLineTools* && -d /Applications/Xcode.app ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi

cleanup() {
  echo "Removing walkthrough demo data…"
  (cd "$BACKEND" && "$PYTHON" manage.py seed_walkthrough --clean) || true
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$OUTPUT"
rm -rf "$OUTPUT/screens" "$OUTPUT/Walkthrough.xcresult" "$OUTPUT/walkthrough.mp4"

# One-time password for the demo users. Never printed or saved.
export CAMPUSOS_WALKTHROUGH_PASSWORD="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(16))')"

echo "Seeding demo data…"
(cd "$BACKEND" && "$PYTHON" manage.py migrate --verbosity 0 && "$PYTHON" manage.py seed_walkthrough)

if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "Using the backend already running on 127.0.0.1:8000."
else
  echo "Starting the backend on 127.0.0.1:8000 (log: $OUTPUT/backend.log)…"
  (cd "$BACKEND" && exec "$PYTHON" manage.py runserver 127.0.0.1:8000 --noreload) >"$OUTPUT/backend.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS "$HEALTH_URL" >/dev/null || { echo "Backend didn't start; see $OUTPUT/backend.log" >&2; exit 1; }
fi

echo "Running the walkthrough on $SIMULATOR (takes a few minutes)…"
TEST_STATUS=0
TEST_RUNNER_UI_PASSWORD="$CAMPUSOS_WALKTHROUGH_PASSWORD" xcodebuild test \
  -project "$REPO/ios/CampusOS.xcodeproj" \
  -scheme CampusOS \
  -destination "platform=iOS Simulator,name=$SIMULATOR" \
  -parallel-testing-enabled NO \
  -only-testing:CampusOSUITests/WalkthroughUITests \
  -resultBundlePath "$OUTPUT/Walkthrough.xcresult" \
  >"$OUTPUT/xcodebuild.log" 2>&1 || TEST_STATUS=$?

if [[ -d "$OUTPUT/Walkthrough.xcresult" ]]; then
  ATTACHMENTS="$(mktemp -d)"
  xcrun xcresulttool export attachments --path "$OUTPUT/Walkthrough.xcresult" --output-path "$ATTACHMENTS" >/dev/null
  # Keep the numbered screenshots ("01-home.png", …) and the screen recording.
  python3 - "$ATTACHMENTS" "$OUTPUT" <<'PY'
import json, re, shutil, sys
from pathlib import Path

source, output = Path(sys.argv[1]), Path(sys.argv[2])
screens = output / "screens"
screens.mkdir(exist_ok=True)
count = 0
for test in json.loads((source / "manifest.json").read_text()):
    for attachment in test["attachments"]:
        name = attachment["suggestedHumanReadableName"]
        exported = source / attachment["exportedFileName"]
        if re.match(r"\d\d-", name) and name.endswith(".png"):
            shutil.copy(exported, screens / (name.split("_0_")[0] + ".png"))
            count += 1
        elif name.endswith(".mp4"):
            shutil.copy(exported, output / "walkthrough.mp4")
print(f"Exported {count} screenshots to {screens}")
PY
  rm -rf "$ATTACHMENTS"
fi

if [[ $TEST_STATUS -ne 0 ]]; then
  echo "The walkthrough reported problems; screenshots above may be incomplete." >&2
  grep -E "error:|Didn't find|No button|No card|No tab" "$OUTPUT/xcodebuild.log" | sort -u | head -20 >&2 || true
  exit "$TEST_STATUS"
fi
echo "Done. Screenshots: $OUTPUT/screens"
# Xcode attaches a screen recording only on some runs.
[[ -f "$OUTPUT/walkthrough.mp4" ]] && echo "Recording: $OUTPUT/walkthrough.mp4"
exit 0
