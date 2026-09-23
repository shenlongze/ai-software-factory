#!/usr/bin/env bash
# Clean-environment "really install, really run" check.
#
# Founder's rule: before any release, install the built artifact in a CLEAN env and run it.
# (editable installs hide packaging bugs -- v1.3.1 empty shell, v1.3.2/v1.3.9 missing
#  data file / index.html, both found only by this kind of check.)
#
# Usage: bash scripts/check_wheel.sh [port]
# Any failing check => exit code non-zero => do NOT release.
set -u
PORT="${1:-8096}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/checkwheel.XXXXXX)"
PIDFILE="$WORK/serve.pid"
FAIL=0
say() { printf '  %s\n' "$*"; }
ok()  { printf '  [OK] %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; FAIL=1; }

cleanup() {
    if [ -f "$PIDFILE" ]; then
        P="$(cat "$PIDFILE" 2>/dev/null || true)"
        if [ -n "${P:-}" ]; then
            kill "$P" 2>/dev/null || true        # exact PID only -- never kill by pattern
            say "stopped service (exact PID $P)"
        fi
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT

cd "$REPO" || exit 1
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || { bad "no $PY (build the repo .venv first)"; exit 1; }

say "1) build wheel"
"$PY" -m pip wheel . -w "$WORK" --no-deps -q || { bad "wheel build failed"; exit 1; }
WHL="$(ls "$WORK"/*.whl 2>/dev/null | head -1)"
if [ -z "$WHL" ]; then bad "no wheel produced"; exit 1; fi
ok "wheel: $(basename "$WHL")"

say "2) install into a clean venv (no repo path involved)"
"$PY" -m venv "$WORK/venv" || { bad "venv creation failed"; exit 1; }
"$WORK/venv/bin/pip" install -q "$WHL" || { bad "install failed"; exit 1; }
ok "installed: $(cd /tmp && "$WORK/venv/bin/factory" -v | head -1)"

say "3) run real commands from the installed artifact"
for C in "project list" "status" "console activity --limit 2" "kanban --limit 1"; do
    if (cd /tmp && "$WORK/venv/bin/factory" $C >/dev/null 2>&1); then
        ok "factory $C"
    else
        bad "factory $C failed"
    fi
done

say "4) start service and probe two endpoints (/ must be 200 -- catches unpackaged data files)"
(cd /tmp && FACTORY_ROOT="${FACTORY_ROOT:-$HOME/.factory}" \
    "$WORK/venv/bin/factory" serve --port "$PORT" >"$WORK/serve.log" 2>&1) &
echo $! > "$PIDFILE"
sleep 7
for P in "/" "/status" "/api/trees"; do
    CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:$PORT$P" || echo 000)"
    if [ "$CODE" = "200" ]; then ok "$P -> HTTP 200"; else bad "$P -> HTTP $CODE (expected 200)"; fi
done

if [ "$FAIL" = 0 ]; then
    say "clean-env install+run: ALL PASS"
    exit 0
fi
say "clean-env install+run: FAILURES ABOVE -- do not release"
exit 1
