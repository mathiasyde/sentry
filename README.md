# Sentry

Sentry is a dynamic analysis tool for hybrid Android apps. It runs an APK under Frida, hooks Android WebView APIs, observes JavaScript bridge behavior, and generates WebView security reports.

Use `analyse.sh` as the entry point for analysis.

```bash
./analyse.sh [--[no-]discover-bridge-interfaces[=true|false]] <APK-FILE> [<APK-PACKAGE>]
```


## Quick Start

Make the entry point executable:

```bash
chmod +x ./analyse.sh
```

Run an APK when you know the package name:

```bash
./analyse.sh path/to/app.apk com.example.app
```

Run an APK and let Sentry extract the package name:

```bash
./analyse.sh path/to/app.apk
```

Package extraction requires `aapt`. It is looked up on `PATH`, then in the newest `$ANDROID_HOME` (or `$ANDROID_SDK_ROOT`) `build-tools/` directory, then at `/opt/homebrew/bin/aapt` or `/usr/local/bin/aapt`.

## Outputs

`analyse.sh` writes all analysis artifacts automatically:

- `logs/output.log`: raw Sentry event stream captured from Frida
- `logs/report.md`: human-readable WebView security report
- `target/output.log`: raw event stream copy used for report generation
- `target/report.json`: machine-readable report with risk score, findings, evidence, WebView inventory, sensitive data flows, and origin-to-bridge map
- `target/static-bridges.json`: JavaScript bridges found by static analysis of the APK (see below)

If no Sentry events are captured, report generation is skipped so empty runs are not mistaken for clean results.

## Static bridge discovery

Before the dynamic run starts, Sentry scans the APK for JavaScript bridges. This is on by default. It finds every method annotated with `@JavascriptInterface`, and every `addJavascriptInterface(object, name)` call with the bridge name JavaScript sees (for example `window.Android`) and the class behind it. Results go to `target/static-bridges.json`, which is written even if the run captures no events.

Every exposed method the scan finds is then hooked as soon as the app starts, so calls to it are logged even if the run never sees the bridge being registered. Framework classes are never hooked.

When a report is generated, it gains a **Static Bridge Inventory** section that labels each bridge:

- `static+runtime`: found in the APK and registered during the run
- `static-only`: found in the APK, but the run never reached the code that registers it. These also get an `info` finding, `WV-STATIC-BRIDGE-UNOBSERVED`, which does not change the risk score.
- `runtime-only`: registered at runtime but not found statically, for example from dynamically loaded code

To turn discovery off:

```bash
./analyse.sh --no-discover-bridge-interfaces path/to/app.apk com.example.app
./analyse.sh --discover-bridge-interfaces=false path/to/app.apk com.example.app
```

With discovery off, the run behaves exactly as it did before this feature. If discovery itself fails (a packed or corrupt APK, for instance), Sentry prints a warning and the dynamic run continues.

To scan an APK without a device:

```bash
PYTHONPATH=sentry python3 -m core.static path/to/app.apk [--out static-bridges.json]
```

Limits: the analysis works within one method at a time. A bridge name built at runtime (concatenated, read from config, or returned by another method) is reported as unresolved, along with where it came from; it is never guessed. Code loaded at runtime (downloaded dex, reflection) shows up only as `runtime-only`. For apps targeting API levels below 17, every public method of a registered object is reported as exposed.

## Project layout

The analysis toolchain lives under `sentry/`, in three areas:

| Directory | What goes there |
|---|---|
| [`sentry/browser/`](sentry/browser/README.md) | Code that runs **inside WebView pages**: the in-page observer, bridge-taint wrappers and the probe. |
| [`sentry/native/`](sentry/native/README.md) | Frida hooks **in the app process**, one module per Android API family (lifecycle, settings, clients, JS bridge, JS evaluation, permissions, environment). |
| [`sentry/core/`](sentry/core/README.md) | Everything else: the event vocabulary, the agent bundler, `analyse.sh` orchestration, static bridge discovery, the Docker and local runners, the report generator and the benchmark runner. |

`analyse.sh`, `scripts/run-benchmarks-linux.sh` and `sentry/report.py` are thin launchers into `sentry/core/`. The Frida agent is built from all three areas into a single script by `sentry/core/agent/build_agent.py`. The local runner does this on every run, and the Docker image does it at build time.

Run the test suite with:

```bash
python3 -m unittest discover -s tests -t .
```

## Runner Modes

`analyse.sh` selects a runner with `SENTRY_RUNNER`.

```bash
SENTRY_RUNNER=auto ./analyse.sh path/to/app.apk com.example.app
SENTRY_RUNNER=docker ./analyse.sh path/to/app.apk com.example.app
SENTRY_RUNNER=local ./analyse.sh path/to/app.apk com.example.app
```

Modes:

- `auto`: default. Uses Docker mode on Linux when `/dev/kvm` exists, otherwise local mode.
- `docker`: uses the Docker Compose Android emulator environment. Requires Linux and `/dev/kvm`.
- `local`: uses a host Android emulator or device through local `adb` and `frida`.

## Linux Docker Mode

Use Docker mode on Linux hosts with KVM:

```bash
SENTRY_RUNNER=docker ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF
```

Requirements:

- Linux with `/dev/kvm`
- Docker and Docker Compose
- Python 3
- `aapt`, unless the package name is passed explicitly

`analyse.sh` starts the required Docker services, installs the APK, starts Frida, captures Sentry events, and generates reports.

## Local Mode

Use local mode on macOS, Linux without Docker emulator support, or when you already have an emulator/device running:

```bash
SENTRY_RUNNER=local ./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF
```

Requirements:

- `adb` on `PATH`
- `frida` on `PATH`
- a booted Android emulator or device visible to `adb`
- `frida-server` installed and executable on the Android device

Local-mode environment variables:

- `SENTRY_ADB_SERIAL`: adb serial for a specific emulator/device
- `SENTRY_FRIDA_DEVICE`: Frida device id
- `SENTRY_FRIDA_SERVER`: device path to `frida-server`, default `/data/local/tmp/frida-server`
- `SENTRY_BOOT_TIMEOUT`: emulator boot wait timeout in seconds, default `120`

Example with a specific adb device:

```bash
SENTRY_RUNNER=local \
SENTRY_ADB_SERIAL=emulator-5554 \
./analyse.sh path/to/app.apk com.example.app
```

## Benchmarks

The `Benchmark/` directory contains benchmark APKs for known WebView update cases. Run each benchmark through the same entry point:

```bash
./analyse.sh Benchmark/JSUpdateCaseD.apk com.example.jsUpdatecaseD
./analyse.sh Benchmark/JsUpdateCaseE.apk com.example.jsUpdatecaseE
./analyse.sh Benchmark/JsUpdateCaseF.apk com.example.jsUpdatecaseF
./analyse.sh Benchmark/JsUpdateCaseG.apk com.example.jsUpdatecaseG
./analyse.sh Benchmark/strongUpdate.apk com.example.strongupdate
./analyse.sh Benchmark/strongUpdatecaseA.apk com.example.strongupdate
./analyse.sh Benchmark/strongUpdatecaseB.apk com.example.strongupdatecaseb
./analyse.sh Benchmark/strongUpdatecaseC.apk com.example.strongupdatecaseC
```

To run all benchmark APKs on a Linux/KVM machine:

```bash
for apk in Benchmark/*.apk; do
  ./analyse.sh "$apk"
done
```

Pass package names explicitly when `aapt` is unavailable.

## Demo APK

The repository includes a demonstration Android/WebView app under `android/` and web content under `web/`. After building the demo APK, analyze it through the same entry point:

```bash
./analyse.sh android/target/app.apk com.example.bachelorproject
```

## Troubleshooting

`Error: Docker emulator mode requires /dev/kvm.`

Use a Linux host with KVM for Docker mode, or use local mode with a host emulator:

```bash
SENTRY_RUNNER=local ./analyse.sh path/to/app.apk com.example.app
```

`Error: adb is not installed` or `Error: frida is not installed`

Install Android platform tools and Frida tools, then rerun `analyse.sh`.

`Error: frida-server was not found`

Install `frida-server` on the Android device or set `SENTRY_FRIDA_SERVER` to the correct device path.

`Failed to find aapt`

Pass the package name explicitly:

```bash
./analyse.sh path/to/app.apk com.example.app
```

or install `aapt` so `analyse.sh` can extract it automatically.

Docker mode still runs old hooks after updating Sentry

An existing `sentry` image keeps the agent it was built with. Rebuild the images after updating:

```bash
docker compose build sentry run-frida-server
```
