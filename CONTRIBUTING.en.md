# Contributing

Thank you for your interest in subwatch! The project is local-first and
minimalist, so a few simple ground rules apply. **Українська версія:
[CONTRIBUTING.md](CONTRIBUTING.md).**

## How to help

- 🐛 Bug reports — via [Bug report](.github/ISSUE_TEMPLATE/bug_report.md).
- 💡 Feature ideas — via [Feature request](.github/ISSUE_TEMPLATE/feature_request.md).
- 🔀 Pull requests are welcome — please follow the steps below.

## Ground rules

1. **Communication languages: Ukrainian or English.** No Russian
   localization and no Russian-language text in code/docs — this is the
   project owner's political decision (see [i18n](#i18n-ukrainian--english)).
2. **Every change ships with a test.** A new endpoint or behavior = a new
   test in `tests/`. Before committing: the full `pytest` run must be green.
3. **One feature = one commit** with a meaningful message.
4. **Privacy-first**: no telemetry, no analytics, no network calls without
   explicit user consent (the optional ECB exchange-rate cache is the only
   exception).
5. **No secrets in code**: configuration happens through environment
   variables (`SUBWATCH_DB`, `SUBWATCH_HOST`, `SUBWATCH_PORT`) with safe
   defaults.
6. UI strings go through the i18n dictionaries (`static/i18n/uk.json`,
   `en.json`) with both translations. Never hardcode text in templates.
7. A11y: new interactive elements get `aria-label`, buttons get
   `type="button"`, tables get `scope="col"`.

## Environment and tests

```bash
pip install -r requirements.txt
pip install -e .          # installs the `subwatch` command
pytest                    # everything must pass (~233 tests)
pytest tests/test_import.py -q   # a single file
```

- Tests use the FastAPI `TestClient` (the `client` fixture in
  `conftest.py`) and a temporary database — no external services needed
  to run them.
- **Optional, the native accelerator**: `dotnet 10 SDK` →
  `dotnet publish dotnet/SubRec -c Release -o dotnet/publish`
  (or `SUBWATCH_NATIVE=/path/to/SubRec.exe`; `SUBWATCH_NATIVE=off`
  disables it). Without it everything runs on pure Python — the tests
  cover both paths.
- Style: no strict linter, but keep the code readable, put types in
  signatures, and comment the "why", not the "what".

## Architecture of the logic (what lives where)

### Statement import and the `detect_recurring` heuristic (backend/csvimport.py)

Pipeline: raw CSV text → `parse_csv()` → `list[Txn]`
(date, description, amount, currency) → `detect_recurring()` → candidates
for the user to confirm (they are shown in the UI; nothing is ever created
automatically).

**Step 1 — description normalization** (`normalize_description`): uppercase,
every digit and punctuation mark replaced with a space, spaces collapsed.
Cyrillic is preserved (`А-ЯІЇЄҐ`). That is why `NETFLIX.COM 8812` and
`NETFLIX.COM 9931` yield the same key `NETFLIX COM` and group together —
card numbers / transaction ids do not split the group.

**Step 2 — grouping**: transactions go into a dict keyed by the normalized
description. Groups with fewer than `MIN_OCCURRENCES = 3` occurrences are
dropped immediately.

**Step 3 — periodicity**: inside a group, sort by date, compute the gaps
between consecutive dates and take the **median**. Known periods are
`KNOWN_PERIODS = (7, 14, 30, 31, 365)`; the closest one is picked when
`|gap − period| ≤ DATE_TOLERANCE` (**±2 days**). Then every individual gap
must fit the tolerance of *at least one* known period — these are the
"calendar-honest" intervals: a monthly charge can gap 28/30/31 days and all
of them pass, while the median still picks the labelling period (30 vs 31).
A skipped month (a 60-day gap) breaks the group — on purpose: better to
miss a subscription than to offer a false one.

**Step 4 — amounts**: `abs(amount)` is used; the median becomes the
candidate's amount. The spread `max − min` inside a group must be
`≤ max(0.02, 5% × median)` (`AMOUNT_TOLERANCE = 0.05`) — the absolute
2-cent floor protects small amounts.

**Step 5 — currency and name**: the currency is the most frequent one in
the group (currencies are never mixed); the name/description is the most
frequent *raw* (pre-normalization) string. The next charge date is computed
via `schedule.add_months`/`add_years` (30/31 → monthly, 365 → yearly,
otherwise custom), and the final candidate list is sorted by amount,
descending.

**Determinism — do not break**: `_most_common()` resolves ties to the
first-encountered value, never by `set`/hash iteration order. This is the
precondition for the **bit-identical parity** with the native port: the
same input must produce the same candidates in Python and in C#, otherwise
golden tests are impossible.

### The native accelerator (backend/native_accel.py + dotnet/SubRec)

`SubRec` is a faithful C# port of `parse_csv()` + `detect_recurring()`
(project `dotnet/SubRec`, build instructions in `dotnet/README.md`). When
the executable is available (`SUBWATCH_NATIVE` or the default
`dotnet/publish/SubRec.exe`), the whole CSV → candidates pipeline runs
through it (~2x on a 50k-row statement); when it is missing, fails, or
`SUBWATCH_NATIVE=off` is set — it silently falls back to pure Python.
`/api/import/analyze` uses the accelerator automatically.

**The parity rule**: any change to the heuristic (`parse_csv`,
`normalize_description`, `detect_recurring`, the constants `KNOWN_PERIODS`,
`DATE_TOLERANCE`, `AMOUNT_TOLERANCE`, `MIN_OCCURRENCES`) must be mirrored
in `dotnet/SubRec/Detect.cs` and `CsvParse.cs` — otherwise the golden and
fuzz parity tests (`tests/test_native_parity.py`) fail. After changing:
both implementations + `pytest tests/test_native_parity.py` + optionally
`scripts/benchmark_native.py`.

### Exchange rates (backend/rates.py)

Daily reference rates from the **ECB** (`eurofxref-daily.xml`, EUR-based:
"units of currency per 1 EUR"). `fetch_rates()` downloads the XML once and
caches it on disk with a 12-hour TTL (`SUBWATCH_RATES_CACHE` overrides the
path). `get_rates()` never raises outwards: the network being down → the
stale cache (a stale rate beats no rate), neither cache nor network → `{}.
`convert()` converts through the EUR base. This is the **only** outbound
network call in the codebase — new ones require explicit user consent.

### ICS export (backend/ics.py)

`build_ics()` produces an RFC 5545-compliant calendar of upcoming charges:
`VCALENDAR 2.0`, **CRLF** line endings, all-day events
(`DTSTART;VALUE=DATE`, `DTEND` = the next day), mandatory `UID` and
`DTSTAMP`, escaping of `\ ; ,` and line breaks in `SUMMARY`/`DESCRIPTION`.
Tests — `tests/test_ics.py`; new event fields come with a test and without
breaking the escaping.

### Family mode (backend/family.py)

A subscription carries `owner`, `payer` and `share_pct` (the payer's
share, %). `family_breakdown()` groups active subscriptions by payer
(`NULL` → "(не вказано)") and computes each payer's share-adjusted
monthly/yearly totals: `monthly_equivalent × share_pct/100`. **Currencies
are never mixed** — totals are kept in separate per-currency dicts.
New family-mode fields only ship with a test in `tests/test_family.py`.

### Cancel assistant (backend/cancel_kb.py)

A static knowledge base for the top-20 subscription services: the official
cancellation URL, keywords, and step-by-step instructions in **both
languages** (`steps_uk`, `steps_en`). No network calls, no scraping — pure
static data, updated with releases. `match_service()` finds a service by
keywords in the transaction description. A new service = a new entry in
`SERVICES` with the URL, keywords and instructions in both languages
(+ a test in `tests/test_cancel_kb.py`).

## How to add a bank preset (step by step)

A preset maps the columns of a specific bank's CSV export onto the
canonical fields (date/description/amount/currency). Existing ones:
`revolut`, `wise`.

1. **Take a real CSV** from the bank and write down the exact header names
   (case does not matter; banks often have several date columns —
   "Started Date" and "Completed Date" in Revolut — then use a list of
   aliases).
2. **Add an entry to `PRESETS`** in `backend/csvimport.py`:

   ```python
   "monobank": {
       "label": "monobank (statement CSV)",
       "columns": {
           "date": ["дата", "date"],
           "description": ["опис", "призначення"],
           "amount": ["сума", "amount"],
           "currency": ["валюта", "currency"],
       },
   },
   ```

   Aliases are matched case-insensitively: exact match first, then
   substring.
3. **Nothing else in the code is needed**: `parse_csv(text, preset_name)`
   picks up the preset, `GET /api/import/presets` lists it, and
   `POST /api/import/analyze` with `"preset": "monobank"` takes the new
   path.
4. **Tests** in `tests/test_presets.py`, modelled on `REVOLUT_CSV`/
   `WISE_CSV`:
   - `/api/import/presets` contains the new preset (label and key);
   - parsing a real statement snippet (dates in the bank's format, the
     currency as a column, negative amounts) finds the recurring payment;
   - a mismatched header / unknown preset yields 422 or `ValueError`.
5. **Date format**: if the bank writes dates in a format missing from
   `_DATE_FORMATS` (`2024-06-01`, `01.06.2024`, `01/06/2024` (day-first
   wins ties), `06/01/2024`, `01-06-2024`, `2024.06.01`, `2024/06/01`,
   `01 Jun 2024`, `Jun 1, 2024`, plus the time cut off ISO timestamps) —
   add the format to `_DATE_FORMATS` with a dedicated test.
6. `pytest tests/test_presets.py tests/test_import.py` — green, then commit.

## How to add a new period (extending 7/14/30/31/365)

Example: a 90-day period. Careful: a new period changes detection for
**all** existing data — parity and tests are required.

1. **`KNOWN_PERIODS`** in `backend/csvimport.py` + the same list in
   `dotnet/SubRec/Detect.cs` (parity! otherwise the golden tests fail).
2. **Think about ambiguities** in `_pick_period`: the median picks the
   closest period, so 90 does not hurt monthly charges (28–33-day gaps
   are still closer to 30), but check the edges: a quarter is really
   89–92 days — ±2 days covers 90±2, and every individual gap must fit
   *at least one* known period. Document the reasoning in a comment.
3. **Mapping to a cycle** in `_next_due()`: a 90-day period is not
   "monthly" — add a branch (e.g. `schedule.add_months(last, 3)` with a
   new cycle label, or `custom` with `custom_days=90`).
4. **API validation**: `SubscriptionIn.cycle` in `backend/main.py` is
   restricted by the pattern `^(monthly|yearly|custom)$`. A new cycle
   label requires extending the pattern, branches in
   `schedule.next_due_date()`, `monthly_equivalent()` (the
   month-normalization coefficient), `upcoming_dates()`/
   `nth_occurrence()`, the SQL ordering in `main.py`, and translations in
   `static/i18n/uk.json` + `en.json`.
   *The simpler path* is to map the new period onto existing cycles
   (custom/monthly) — then the API does not change.
5. **Tests**: detection of the new period (≥3 occurrences, realistic
   gaps) in `tests/test_import.py`, cycle/equivalent in
   `tests/test_schedule.py`, Python↔C# parity in
   `tests/test_native_parity.py` (add a case to the golden/fuzz fixtures).
6. Update the period mentions in `README.md`/`README.en.md` and the
   CHANGELOG.

## Branches

- **`master`** — the stable branch. Every push runs CI
  (`.github/workflows/tests.yml`, Python 3.12 and 3.13). Small direct
  commits are fine; for anything bigger — a feature branch and a PR.
- **`mobile/android-ios`** — the mobile shells (Capacitor 6): `android/`,
  `ios/`, `mobile/` (the server-address splash screen), the
  `android-build.yml` (APK) and `ios-build.yml` (unsigned, for
  AltStore/Sideloadly) workflows. Backend changes are made on `master` and
  land here via merge; mobile code must not break the backend — `pytest`
  green in both branches before every push.

## Pull requests and commits

1. Fork/feature branch → the change **with a test** → the full `pytest`
   run green.
2. One logical feature = one commit; messages in Ukrainian or English,
   following the project's history style: `Feature: …`, `Fix: …`,
   `Tests: …`, `Docs: …`, `Mobile: …`, `OSS: …`.
3. A PR with a short "what and why"; CI must be green before review.
4. Private data (real statements, keys) never lands in tests/fixtures.

## i18n (Ukrainian + English)

- All UI strings live in `static/i18n/uk.json` and `en.json`; a key is
  added to **both** dictionaries in the same commit
  (`tests/test_i18n.py` watches this).
- **Never add a Russian localization (`ru.json`, `ru-RU`)** — a political
  decision of the project owner; the hygiene tests make sure it never
  appears.
- English texts are natural English, Ukrainian texts are natural
  Ukrainian; do not calque one from the other.
- The A11y rules (rule 7) apply to new i18n elements too.

## License

By submitting a pull request you agree your contribution is licensed under
the project's [MIT license](LICENSE).
