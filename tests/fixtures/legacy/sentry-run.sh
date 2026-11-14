#!/bin/sh
set -eu

set -a
. /sentry/target/.env
set +a

adb connect emulator:5555

adb forward tcp:27042 tcp:27042 # forward frida server port
adb reverse tcp:5173 tcp:5173 # open for web server
frida -H 127.0.0.1:27042 -f "$APP_PACKAGE" -l /sentry/hooks/webview.js -l /sentry/hooks/getenv.js
