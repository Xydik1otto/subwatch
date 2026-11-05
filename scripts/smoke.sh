#!/usr/bin/env sh
# Smoke test: запускає uvicorn на випадковому порті, перевіряє головні
# ендпоінти, завершує сервер, виводить PASS/FAIL.
set -u

cd "$(dirname "$0")/.."

PORT="${SMOKE_PORT:-$(( (RANDOM % 2000) + 8000 ))}"
BASE="http://127.0.0.1:${PORT}"
# mktemp -d gives MSYS paths git-bash can't hand to native Python; let
# Python create the temp dir itself so the path is Windows-native.
DB="$(python -c 'import tempfile;print(tempfile.mkdtemp())')/smoke.db"

fail() { echo "FAIL: $1"; kill "${srv:-0}" 2>/dev/null; wait 2>/dev/null; exit 1; }

SUBWATCH_DB="$DB" python -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" &
srv=$!

i=0
while [ "$i" -lt 60 ]; do
    curl -sf "$BASE/api/health" >/dev/null 2>&1 && break
    i=$((i + 1))
    sleep 0.5
done
[ "$i" -lt 60 ] || fail "server did not start on port $PORT"

check() { # check <path> <expected-substring>
    curl -sf "$BASE$1" 2>/dev/null | grep -q "$2" || fail "GET $1: '$2' not found"
}

check /api/health '"status":"ok"'

curl -sf -X POST "$BASE/api/subscriptions" -H 'Content-Type: application/json' \
     -d '{"name":"Netflix","amount":15.49,"currency":"USD","cycle":"monthly","next_due_date":"2026-11-05"}' \
     | grep -q '"name":"Netflix"' || fail "POST /api/subscriptions"

check /api/subscriptions 'Netflix'
check /api/summary 'monthly_by_currency'
check /api/upcoming 'charge'
check /api/export.ics 'BEGIN:VCALENDAR'
check /api/worst-offenders 'Netflix'
check /api/projection 'months'
check /api/import/presets 'revolut'
check / 'og:title'

kill "$srv" 2>/dev/null
wait "$srv" 2>/dev/null
rm -rf "${DB%/*}"
echo "PASS: all smoke checks on port $PORT"
