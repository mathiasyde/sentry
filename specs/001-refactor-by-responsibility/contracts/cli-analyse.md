# Contract: `analyse.sh` and the benchmark runner

The rules below must hold before and after the refactor (FR-001, FR-002, FR-006), except for the intentional deviations listed at the end.

## `./analyse.sh <APK-FILE> [<APK-PACKAGE>]`

It is run from the repository root, using `/bin/sh`.

### Steps, in order (messages are exact)
1. Print `Sentry - version alpha` followed by an empty line.
2. If `python3` is missing, print `Error: python3 is not installed` and exit 1.
3. If no APK argument is given, print `Usage: $0 <apk> [<apk-package>]` and exit 1. If the file is missing, print `File not found: <apk>` and exit 1.
4. If no package name is given, find `aapt`. If it can't be found, print `Failed to find aapt. Install it with Homebrew or provide the APK package name.` and exit 1.
5. If the package name comes out empty, print `Failed to extract package name from apk` and exit 1.
6. Read `SENTRY_RUNNER` (`auto` by default, or `docker` or `local`). `auto` picks `docker` on Linux when `/dev/kvm` is a character device, and `local` otherwise. Any other value prints `Error: invalid SENTRY_RUNNER '<v>' (expected auto, docker, or local)` and exits 1.
7. In docker mode, if `docker-compose.yml` is missing, print `Error: docker-compose.yml not found` and exit 1.
8. Prepare the workspace:
   - `mkdir -p target logs`
   - copy the APK to `target/app.apk`
   - `touch target/output.log`
   - `rm -f target/report.json logs/report.md`
   - write `APP_PACKAGE=<pkg>` to `target/.env`
9. Set the traps: `EXIT` calls `generate_report`, `INT` exits 130, `TERM` exits 143.
10. Run the selected runner. Each runner tees the agent's stdout to both `target/output.log` and `logs/output.log`.
11. `generate_report` runs on exit and only once:
    - if `target/output.log` is non-empty, run the report CLI with `--json target/report.json --markdown logs/report.md`; a failure is ignored (`|| true`);
    - otherwise print `Report skipped: no Sentry events were captured`.

### Docker runner
- If `docker` is missing, print `Error: docker is not installed` and exit 1.
- Without KVM, print the two-line `/dev/kvm` error and exit 1.
- Run `docker compose down`, then `docker compose up -d emulator run-frida-server sentry`, then `docker logs -f sentry | tee …`.

### Local runner
- If `adb` or `frida` is missing, print the matching "not installed" errors and exit 1.
- Print `Using local emulator mode`. Without KVM, also print the notice line.
- If no device is visible, print a two-line error and exit 1.
- Wait for `sys.boot_completed`, up to `SENTRY_BOOT_TIMEOUT` seconds (120 by default). On timeout, print the error and exit 1.
- Run `adb install -r target/app.apk`, then `adb reverse tcp:5173 tcp:5173` (best effort).
- Check that `SENTRY_FRIDA_SERVER` (default `/data/local/tmp/frida-server`) exists and is executable; otherwise print a two-line error and exit 1. Start it if it is not running, then sleep 2 s.
- Spawn with `frida -D $SENTRY_FRIDA_DEVICE` if that variable is set, otherwise with `frida -U`, using `-f <pkg>`.
- `SENTRY_ADB_SERIAL`, when set, adds `-s <serial>` to every adb call.

### Changed internals (not observable)
- `analyse.sh` is a launcher. It checks for `python3`, printing the banner and `Error: python3 is not installed` if it is missing. Otherwise it runs `exec python3 -m core.run "$@"` with `SENTRY_PROG="$0"`, so the usage line still shows how the script was invoked. Orchestration lives in `sentry/core/run/` and `sentry/core/runners/` (research R11).
- The agent is now **one** generated file. The local runner builds it with `python3 sentry/core/agent/build_agent.py --out target/agent.js` just before spawning, then loads it with `-l target/agent.js` instead of the two `-l` hook files. If the build fails, the runner prints `Error: failed to build Sentry agent` and exits 1. This is a new error path that cannot happen with a correct checkout.
- The Docker image builds `/sentry/build/agent.js` when the image is built.

## `scripts/run-benchmarks-linux.sh [benchmark-dir]`

Everything stays the same:
- the usage text and `-h/--help`;
- the environment variables `SENTRY_BENCHMARK_SECONDS` (default 600), `SENTRY_BENCHMARK_RESULTS` (default `benchmark-results`), `SENTRY_BENCHMARK_DIR` and `SENTRY_KEEP_CONTAINERS`;
- the Linux and KVM preconditions;
- the per-APK layout: `benchmark-results/<name>/{status.txt,runner.log,output.log,logs-output.log,report.json,report.md}`;
- the status values `completed`, `timed_out` and `failed_<rc>`.

## Intentional deviations

The project owner approved these on 2026-10-16, as the FR-001 exception. See [research.md R5](../research.md#r5-splitting-the-shell-scripts-and-sharing-helpers).

| Helper | Before | After (shared `sentry/core/run/package.py`) |
|---|---|---|
| `find_aapt` | `analyse.sh` searched `PATH`, then Homebrew. The benchmark runner searched `PATH`, then SDK `build-tools`. | Both search `PATH`, then the newest `$ANDROID_HOME`/`$ANDROID_SDK_ROOT` `build-tools/*/aapt`, then `/opt/homebrew/bin/aapt` and `/usr/local/bin/aapt`. The fallback list can be overridden with the **internal, undocumented** variable `SENTRY_AAPT_FALLBACKS`, which exists only for tests and is not part of the user-facing contract. |
| Package name | `analyse.sh` used `grep package \| cut -d' ' -f2 \| cut -d"'" -f2`, which could return several lines. | Both use `sed -n "s/^package: name='\([^']*\)'.*/\1/p" \| head -n 1`. |

Neither change can turn a run that succeeded into one that fails. The error messages stay specific to each caller: `analyse.sh` keeps its Homebrew hint, and the benchmark runner keeps its SDK hint.
