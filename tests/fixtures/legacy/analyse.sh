#!/bin/sh

echo "Sentry - version alpha"
echo ""

KVM_AVAILABLE=0
if [ -c /dev/kvm ]; then
  KVM_AVAILABLE=1
fi

check_missing_commands() {
  missing=0

  for cmd in "$@"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "Error: $cmd is not installed"
      missing=$((missing + 1))
    fi
  done

  if [ "$missing" -gt 0 ]; then
    exit 1
  fi
}

find_aapt() {
  if command -v aapt >/dev/null 2>&1; then
    command -v aapt
    return 0
  fi

  for candidate in /opt/homebrew/bin/aapt /usr/local/bin/aapt; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

check_missing_commands python3

# make sure the apk is provided
APK_INPUT="$1"
if [ "$APK_INPUT" = "" ]; then
    echo "Usage: $0 <apk> [<apk-package>]"
    exit 1
fi

if [ ! -f "$APK_INPUT" ]; then
    echo "File not found: $APK_INPUT"
    exit 1
fi

APP_PACKAGE="$2"

# extract package name from apk if not provided
if [ "$APP_PACKAGE" = "" ]; then
  AAPT_BIN=$(find_aapt)

  if [ "$AAPT_BIN" = "" ]; then
    echo "Failed to find aapt. Install it with Homebrew or provide the APK package name."
    exit 1
  fi

  APP_PACKAGE=$("$AAPT_BIN" dump badging "$APK_INPUT" | grep package | cut -d' ' -f2 | cut -d"'" -f2)
fi

if [ "$APP_PACKAGE" = "" ]; then
  echo "Failed to extract package name from apk"
  exit 1
fi

RUNNER="${SENTRY_RUNNER:-auto}"
case "$RUNNER" in
  auto)
    if [ "$(uname -s)" = "Linux" ] && [ "$KVM_AVAILABLE" -eq 1 ]; then
      RUNNER=docker
    else
      RUNNER=local
    fi
    ;;
  docker|local)
    ;;
  *)
    echo "Error: invalid SENTRY_RUNNER '$RUNNER' (expected auto, docker, or local)"
    exit 1
    ;;
esac

# detect docker compose file
if [ "$RUNNER" = "docker" ] && [ ! -f docker-compose.yml ]; then
    echo "Error: docker-compose.yml not found"
    exit 1
fi

mkdir -p ./target
mkdir -p ./logs
cp "$APK_INPUT" ./target/app.apk
touch ./target/output.log
rm -f ./target/report.json ./logs/report.md
echo "APP_PACKAGE=$APP_PACKAGE" > ./target/.env

REPORT_GENERATED=0

generate_report() {
  if [ "$REPORT_GENERATED" -eq 1 ]; then
    return
  fi
  REPORT_GENERATED=1

  if [ -s ./target/output.log ]; then
    python3 ./sentry/report.py ./target/output.log \
      --json ./target/report.json \
      --markdown ./logs/report.md || true
  else
    echo "Report skipped: no Sentry events were captured"
  fi
}

trap generate_report EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_docker() {
  check_missing_commands docker

  if [ "$KVM_AVAILABLE" -ne 1 ]; then
    echo "Error: Docker emulator mode requires /dev/kvm."
    echo "Use SENTRY_RUNNER=local with a running Android emulator on macOS or hosts without KVM."
    exit 1
  fi

  docker compose down
  docker compose up -d emulator run-frida-server sentry

  docker logs -f sentry | tee ./target/output.log ./logs/output.log
}

adb_cmd() {
  if [ "${SENTRY_ADB_SERIAL:-}" != "" ]; then
    adb -s "$SENTRY_ADB_SERIAL" "$@"
  else
    adb "$@"
  fi
}

run_local() {
  check_missing_commands adb frida

  echo "Using local emulator mode"
  if [ "$KVM_AVAILABLE" -ne 1 ]; then
    echo "Docker/KVM is unavailable; using the host Android emulator via adb."
  fi

  if ! adb_cmd get-state >/dev/null 2>&1; then
    echo "Error: no Android emulator/device is visible to adb."
    echo "Start an emulator first, or set SENTRY_RUNNER=docker on a Linux host with /dev/kvm."
    exit 1
  fi

  boot_wait="${SENTRY_BOOT_TIMEOUT:-120}"
  while [ "$boot_wait" -gt 0 ]; do
    if [ "$(adb_cmd shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
      break
    fi
    sleep 2
    boot_wait=$((boot_wait - 2))
  done

  if [ "$boot_wait" -le 0 ]; then
    echo "Error: Android emulator did not finish booting within ${SENTRY_BOOT_TIMEOUT:-120}s"
    exit 1
  fi

  echo "Installing APK..."
  adb_cmd install -r ./target/app.apk
  adb_cmd reverse tcp:5173 tcp:5173 >/dev/null 2>&1 || true

  frida_server="${SENTRY_FRIDA_SERVER:-/data/local/tmp/frida-server}"
  if ! adb_cmd shell "test -x '$frida_server'" >/dev/null 2>&1; then
    echo "Error: frida-server was not found at $frida_server on the emulator."
    echo "Install it first, or set SENTRY_FRIDA_SERVER to the correct device path."
    exit 1
  fi

  if ! adb_cmd shell "pgrep -f '$frida_server' >/dev/null 2>&1"; then
    echo "Starting frida-server..."
    adb_cmd shell "$frida_server >/dev/null 2>&1 &"
    sleep 2
  fi

  if [ "${SENTRY_FRIDA_DEVICE:-}" != "" ]; then
    frida -D "$SENTRY_FRIDA_DEVICE" -f "$APP_PACKAGE" \
      -l ./sentry/hooks/webview.js \
      -l ./sentry/hooks/getenv.js \
      | tee ./target/output.log ./logs/output.log
  else
    frida -U -f "$APP_PACKAGE" \
      -l ./sentry/hooks/webview.js \
      -l ./sentry/hooks/getenv.js \
      | tee ./target/output.log ./logs/output.log
  fi
}

case "$RUNNER" in
  docker)
    run_docker
    ;;
  local)
    run_local
    ;;
esac
