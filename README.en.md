# subwatch

![tests](https://github.com/bigpi/subwatch/actions/workflows/tests.yml)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![version](https://img.shields.io/badge/version-1.0.0-orange)

[🇺🇦 Українська](README.md) | **English**

Local-first subscription tracker. No cloud, no accounts, no telemetry —
all data lives in a single SQLite file on your disk. Python + FastAPI.

## Features (v1.0.0)

- Subscription CRUD, sorting, monthly-equivalent, yearly totals.
- **Correct dates**: month-end anchor (Jan 31 → Feb 28/29 → Mar 31),
  leap years, custom cycles in days.
- Charge calendar for 30/60/90 days, CLI reminders, ICS export (RFC 5545),
  trial tracker.
- **Bank statement CSV import** with automatic detection of recurring
  payments (7/14/30/31/365-day periods ±2) → candidates to confirm.
- **Price history**: every amount change is recorded —
  `Netflix: 15.49→16.99 (+9.7% over 8 months)`.
- **Cost-per-use**: what one use of a subscription actually costs.
- **Cancel assistant**: a static knowledge base for the top-20 services
  (Netflix, Spotify, Disney+, Adobe…) with official cancellation links and
  step-by-step instructions in Ukrainian and English
  (`GET /api/cancel-assistant`, per-subscription matching via
  `GET /api/subscriptions/{id}/cancel-guide`).
- **Price-change alerts**: every amount change lands in an outbox
  (`GET /api/alerts`), the UI shows a 🔔 badge and an "↑ price changed" mark
  on the affected row until you dismiss it.
- **Family mode**: `owner`, `payer` and `share_pct` fields on every
  subscription; `GET /api/family` totals who pays what, share-adjusted,
  per currency.
- **Multi-currency summary via ECB rates**: `GET /api/summary?base=USD`.
- **Worst offenders**, pause/unpause, annual projection (JSON + SVG),
  tag analytics (JSON + SVG pie), PWA with web notifications.
- **One-click data export**: `GET /api/export.json` (everything: subscriptions,
  price history, alerts) and `GET /api/export.csv`; destructive actions warn
  first.
- **Bilingual UI (UA/EN)**: language switcher in the interface, browser-language
  auto-detection, choice saved locally. No Russian localization — by design.

## Why this exists

> «Consumers estimate they spend **$86** per month on subscriptions —
> but they actually spend **$219** every month.»
> — West Monroe, national consumer survey (2021)

Subscriptions are designed to be forgotten:

- **42%** of people forget about a paid subscription (Capterra, 2024).
- **$17/mo** — average spend on unused subscriptions (CNET, 2025).
- **44%** of users report "subscription fatigue".
- Meanwhile the market moves the other way: one-time purchases grow
  at **+6%/year**.

Cloud subscription trackers (Rocket Money, BillShark etc.) require access to
your bank data — a new risk to solve a problem that can be solved locally,
with a list and dates.

## Quick start

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload       # http://127.0.0.1:8000
pytest                                  # the math is under test
```

See [INSTALL.md](INSTALL.md) for a step-by-step guide for non-programmers
(Windows autostart, Linux systemd user unit, updates).

### Usage

```bash
# add a subscription (monthly/yearly/custom; custom needs custom_days)
curl -X POST localhost:8000/api/subscriptions -H 'content-type: application/json' \
  -d '{"name":"Netflix","amount":15.49,"currency":"USD","cycle":"monthly","next_due_date":"2026-12-01"}'

# list (sort: next_due_date | amount | monthly | name)
curl "localhost:8000/api/subscriptions?sort=next_due_date"

# summary: monthly/yearly equivalent per currency
curl localhost:8000/api/summary

# charge calendar for 30/60/90 days
curl "localhost:8000/api/upcoming?days=90"

# trials ending within 3 days (the "cancel or pay" list)
curl localhost:8000/api/trials

# a charge happened — roll the due date one cycle forward
curl -X POST localhost:8000/api/subscriptions/1/mark-paid

# cost-per-use: monthly cost / times used
curl -X POST localhost:8000/api/subscriptions -H 'content-type: application/json' \
  -d '{"name":"Gym","amount":30,"cycle":"monthly","next_due_date":"2026-12-01","times_used_per_month":12}'

# export all upcoming charges to your calendar
curl -o subwatch.ics localhost:8000/api/export.ics

# full data export (JSON / CSV)
curl -o subwatch-export.json localhost:8000/api/export.json
curl -o subwatch-export.csv localhost:8000/api/export.csv
```

### Bank statement import (CSV)

```bash
# step 1: auto-detect recurring payments (7/14/30/31/365-day periods ±2)
curl -X POST localhost:8000/api/import/analyze -H 'content-type: application/json' \
  -d '{"csv":"date,description,amount\n2026-01-01,NETFLIX.COM,15.49\n2026-02-01,NETFLIX.COM,15.49\n2026-03-01,NETFLIX.COM,15.49"}'

# step 2: confirm the found candidates -> subscriptions are created
curl -X POST localhost:8000/api/import/confirm -H 'content-type: application/json' \
  -d '{"candidates":[{"name":"Netflix","amount":15.49,"cycle":"monthly","next_due_date":"2026-04-01"}]}'
```

The parser understands `;`/`,`/tab separators, Ukrainian and English headers
(`Дата/Опис/Сума`), date formats `YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`,
decimal commas (`16,99`), thousands spaces (`1 234,56`), minus signs and
brackets.

### Native detection accelerator (C#, optional)

The recurring-payment detection engine has a C# port (`dotnet/SubRec`,
a .NET 10 CLI, `SubRec.exe`). When the exe is built, `/api/import/analyze`
and `backend/native_accel.py` run the whole parse + detect pipeline through
it — on a synthetic **50 000-row** statement that is ~**0.4 s** vs ~**0.7 s**
for pure Python (measurements: `python scripts/benchmark_native.py`):

| path on 50 000 rows              | time   |
|----------------------------------|--------|
| Python parse + detect            | 0.74 s |
| SubRec.exe end-to-end            | 0.36 s |
| `/api/import/analyze` (native)   | 0.39 s |
| Python detect without parsing    | 0.12 s |

Without the exe (or with `SUBWATCH_NATIVE=off`) everything runs on pure
Python — results are identical (golden/fuzz tests in
`tests/test_native_parity.py`).

```bash
dotnet publish dotnet/SubRec -c Release -o dotnet/publish   # once
# SubRec.exe also works standalone: stdin CSV -> stdout JSON
./dotnet/publish/SubRec.exe < statement.csv > candidates.json
```

### Cancel assistant

```bash
# catalogue of the top-20 services with official cancel pages
curl localhost:8000/api/cancel-assistant

# step-by-step guide for one service (UA + EN)
curl localhost:8000/api/cancel-assistant/netflix

# match one of your subscriptions to a guide
curl localhost:8000/api/subscriptions/1/cancel-guide
```

### Price-change alerts (outbox)

```bash
curl localhost:8000/api/alerts              # unseen alerts (the outbox)
curl localhost:8000/api/alerts/count        # {"unseen": N} — drives the UI badge
curl -X POST localhost:8000/api/alerts/1/seen
curl -X POST localhost:8000/api/alerts/seen-all
```

### Family mode

```bash
# owner/payer/share on create
curl -X POST localhost:8000/api/subscriptions -H 'content-type: application/json' \
  -d '{"name":"Netflix","amount":15.49,"cycle":"monthly","next_due_date":"2026-12-01","owner":"family","payer":"Taras","share_pct":50}'

# who pays what: share-adjusted totals per payer, per currency
curl localhost:8000/api/family
```

### CLI reminders (local, no daemon)

```bash
python -m backend.remind --days 7            # what will be charged this week
python -m backend.remind --days 7 --notify   # + local notification popup (Windows)
```

### Calendar

`/api/export.ics` generates an RFC 5545 VCALENDAR with one event per upcoming
charge (and trial end) — import it into Google Calendar / Outlook /
Apple Calendar and the reminders arrive where you already look.

## Principles

1. **100% local data.** A single SQLite file is the only "database". No
   external calls (even exchange rates are disk-cached and work offline).
2. **Correct dates.** Month-end edge cases are handled with an anchor: a
   subscription due on the 31st stays "on the 31st" (Jan 31 → Feb 28/29 →
   Mar 31) instead of drifting to the 28th forever. Leap-year Feb 29 is
   handled too.
3. **Monthly-equivalent** — an honest normalisation of yearly (÷12) and
   custom cycles (365.25/days) so subscriptions can be compared fairly.

## Contributing

This project is open source: read [CONTRIBUTING.md](CONTRIBUTING.md) before
opening a pull request (languages: Ukrainian/English; every change ships
with a test; privacy-first). Security — [SECURITY.md](SECURITY.md);
bug reports go through the templates in `.github/ISSUE_TEMPLATE/`.

### Recommended GitHub topics

`subscription-tracker` `local-first` `privacy` `self-hosted` `fastapi`
`python` `sqlite` `personal-finance` `budget` `pwa` `offline-first`
`selfhosted` `money-management`

## License

MIT — see [LICENSE](LICENSE).
