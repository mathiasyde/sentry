#!/usr/bin/env bash
set -u -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCHMARK_DIR="${SENTRY_BENCHMARK_DIR:-}"
RESULTS_DIR="${SENTRY_BENCHMARK_RESULTS:-"$ROOT_DIR/benchmark-results"}"
RUN_SECONDS="${SENTRY_BENCHMARK_SECONDS:-600}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [benchmark-dir]

Runs every APK in the benchmark directory through analyse.sh on Linux.

Environment:
  SENTRY_BENCHMARK_SECONDS   Per-APK timeout in seconds (default: 600)
  SENTRY_BENCHMARK_RESULTS   Output directory (default: benchmark-results)
  SENTRY_BENCHMARK_DIR       Benchmark directory override
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is not installed"
}

find_aapt() {
  if command -v aapt >/dev/null 2>&1; then
    command -v aapt
    return 0
  fi

  local sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
  if [ -n "$sdk_root" ] && [ -d "$sdk_root/build-tools" ]; then
    find "$sdk_root/build-tools" -maxdepth 2 -type f -name aapt -perm -111 \
      | sort -V \
      | tail -n 1
    return 0
  fi

  return 1
}

package_name() {
  local apk="$1"
  "$AAPT_BIN" dump badging "$apk" \
    | sed -n "s/^package: name='\([^']*\)'.*/\1/p" \
    | head -n 1
}

archive_outputs() {
  local apk="$1"
  local package="$2"
  local status="$3"
  local runner_log="$4"
  local name
  name="$(basename "$apk" .apk)"

  local out_dir="$RESULTS_DIR/$name"
  mkdir -p "$out_dir"
  rm -f \
    "$out_dir/status.txt" \
    "$out_dir/runner.log" \
    "$out_dir/output.log" \
    "$out_dir/logs-output.log" \
    "$out_dir/report.json" \
    "$out_dir/report.md"

  {
    echo "apk=$apk"
    echo "package=$package"
    echo "status=$status"
    echo "seconds=$RUN_SECONDS"
  } >"$out_dir/status.txt"

  cp "$runner_log" "$out_dir/runner.log"
  [ -f "$ROOT_DIR/target/output.log" ] && cp "$ROOT_DIR/target/output.log" "$out_dir/output.log"
  [ -f "$ROOT_DIR/logs/output.log" ] && cp "$ROOT_DIR/logs/output.log" "$out_dir/logs-output.log"
  [ -f "$ROOT_DIR/target/report.json" ] && cp "$ROOT_DIR/target/report.json" "$out_dir/report.json"
  [ -f "$ROOT_DIR/logs/report.md" ] && cp "$ROOT_DIR/logs/report.md" "$out_dir/report.md"
}

run_one() {
  local apk="$1"
  local package="$2"
  local log_file
  local status
  local rc

  log_file="$(mktemp)"
  echo "==> $(basename "$apk") ($package)"

  (
    cd "$ROOT_DIR" || exit 1
    SENTRY_RUNNER=docker timeout -s INT "$RUN_SECONDS" ./analyse.sh "$apk" "$package"
  ) >"$log_file" 2>&1
  rc=$?

  if [ "$rc" -eq 0 ]; then
    status="completed"
  elif [ "$rc" -eq 124 ] || [ "$rc" -eq 130 ]; then
    status="timed_out"
  else
    status="failed_$rc"
  fi

  archive_outputs "$apk" "$package" "$status" "$log_file"
  rm -f "$log_file"
  echo "<== $(basename "$apk"): $status"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ -n "${1:-}" ]; then
  BENCHMARK_DIR="$1"
elif [ -z "$BENCHMARK_DIR" ]; then
  if [ -d "$ROOT_DIR/Benchmark" ]; then
    BENCHMARK_DIR="$ROOT_DIR/Benchmark"
  else
    BENCHMARK_DIR="$ROOT_DIR/benchmarks"
  fi
fi

[ "$(uname -s)" = "Linux" ] || die "this benchmark runner is intended for Linux"
[ -c /dev/kvm ] || die "/dev/kvm is required for Docker emulator mode"
[ -d "$BENCHMARK_DIR" ] || die "benchmark directory not found: $BENCHMARK_DIR"

require_command docker
require_command timeout
require_command python3
docker compose version >/dev/null 2>&1 || die "docker compose is not available"

AAPT_BIN="$(find_aapt)"
[ -n "$AAPT_BIN" ] || die "aapt is required on PATH or under ANDROID_HOME/ANDROID_SDK_ROOT"

mkdir -p "$RESULTS_DIR"

shopt -s nullglob
apks=("$BENCHMARK_DIR"/*.apk)
shopt -u nullglob
[ "${#apks[@]}" -gt 0 ] || die "no APK files found in $BENCHMARK_DIR"

for apk in "${apks[@]}"; do
  package="$(package_name "$apk")"
  [ -n "$package" ] || die "could not extract package name from $apk"
  run_one "$apk" "$package"
done

if [ "${SENTRY_KEEP_CONTAINERS:-0}" != "1" ]; then
  (cd "$ROOT_DIR" && docker compose down >/dev/null 2>&1) || true
fi
