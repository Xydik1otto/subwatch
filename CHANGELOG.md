# Changelog

Формат базується на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
і проєкт дотримується [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Spending trends по місяцях**: `backend/trends.py` + `GET /api/trends?months=N`
  — фактичні списання за останні N місяців (дзеркало projection, але назад),
  помісячні суми по валютах (валюти не змішуються), середнє за вікно,
  `delta_pct` і напрямок тренду останнього місяця проти середнього
  (up/flat/down, поріг ±5%).
- **Імпорт виписок у форматі JSON** (поряд із CSV): `parse_json_statement()`
  і формат-агностичний `parse_statement()` у `backend/csvimport.py`;
  `/api/import/analyze` автоматично розпізнає JSON (список об'єктів,
  `{"transactions": [...]}`, `{"statement": {"transactions": [...]}}`,
  `{"data": [...]}`; вкладені `amount.value/amount.currency` у стилі
  Monzo/Starling) і повертає тих самих кандидатів повторюваних платежів.
- **Cancel reminders за N днів до списання**: `POST
  /api/subscriptions/{id}/cancel-reminder` виводить дедлайн скасування
  автоматично як `next_due_date - N` (колонка `cancel_days_before`), а
  `GET /api/cancel-reminders?days=N` — список «встигнути скасувати».
  Дедлайн перераховується при mark-paid (їде разом зі списанням) і,
  як і раніше, потрапляє в .ics (подія CANCEL BEFORE).
- **Нативний акселератор детекції (C# / .NET 10)**: `dotnet/SubRec` —
  CLI-порт рушія повторюваних платежів (`parse_csv` + `detect_recurring`):
  нормалізація описів, групування, періоди 7/14/30/31/365 днів ±2,
  ≥3 входження, розкид сум ≤5%, відсіювання пропущених місяців.
  stdin CSV → stdout JSON; self-contained publish (`dotnet/publish/`),
  працює без інстальованого .NET.
- `backend/native_accel.py`: `/api/import/analyze` використовує exe, коли він
  є (`SUBWATCH_NATIVE` або `dotnet/publish/SubRec.exe`), інакше — чистий
  Python; кандидати ідентичні на біт (golden/fuzz-тести,
  `tests/test_native_parity.py`). `SUBWATCH_NATIVE=off` вимикає нативний шлях.
- `scripts/benchmark_native.py`: заміри Python vs нативний рушій на
  синтетичній виписці 50 000 рядків (~0.74 с проти ~0.36 с, ≈2×).

### Changed
- Детекція стала детермінованою: `name`/`description`/валюта кандидата при
  однаковій частоті беруть «перший зустрінутий» опис (раніше вибір залежав
  від порядку множини, тобто від hash seed процесу). Потрібно для
  біт-ідентичного паритету з нативним портом.

## [1.0.0] - 2026-11-05

«Готово для чужих користувачів»: запускається стороннім користувачем
за 5 хвилин без знання коду.

### Added
- **Cancel assistant**: статична база знань топ-20 сервісів (Netflix,
  Spotify, Disney+, Adobe, ChatGPT Plus…) — покрокові інструкції скасування
  UA/EN + офіційні лінки на сторінки скасування
  (`/api/cancel-assistant`, `/api/subscriptions/{id}/cancel-guide`, секція в UI).
- **Цінові алерти**: кожна зміна amount потрапляє в outbox (`/api/alerts`),
  бейдж 🔔 із кількістю непрочитаних і мітка «↑ ціна змінилась» у рядку
  підписки; `seen` / `seen-all` / `count`.
- **Family mode**: поля `owner` / `payer` / `share_pct` у підписок,
  `/api/family` — зведення «хто платить скільки» з частками, окремо по
  валютах; колонка «Хто платить» в UI.
- **i18n UA/EN**: JSON-словники, перемикач UA/EN в інтерфейсі, авто-детект
  мови браузера, збереження вибору. Російську локалізацію не додано
  (політичне рішення) — тест-гард у `test_readme_bilingual.py` / `test_i18n.py`.
- **First-run demo**: opt-in демо-дані на порожній БД (`POST /api/demo/seed`,
  банер «Завантажити демо»).
- **Експорт даних one-click**: `/api/export.json` (підписки + історія цін +
  алерти) і `/api/export.csv`; попередження (confirm) при видаленні.
- **A11y**: aria-label на інтерактивних елементах, `scope="col"`,
  `role="img"` для emoji-лого, focus-visible стилі, live-регіони.
- **Packaging**: `pyproject.toml` з повними metadata, console-script
  `subwatch` (`SUBWATCH_HOST`/`SUBWATCH_PORT` через env, дефолт 127.0.0.1:8000),
  `pip install -e .` працює.
- **INSTALL.md**: покрокова інструкція для не-програміста — Windows
  (start.bat, автозапуск у папці Startup), Linux (systemd user unit),
  оновлення, резервна копія.
- **README.en.md**: повний англійський README, крос-лінки UA↔EN.
- **Open-source hygiene**: `CONTRIBUTING.md`, `SECURITY.md`, GitHub issue
  templates (UA/EN), `.gitignore` покриває `.env`, README: Contributing +
  рекомендовані GitHub topics; тест-скан репозиторію на витоки приватності
  (шляхи, токени, персональні дані).

## [0.4.0] - 2026-11-05

### Added
- PWA: manifest + service worker, web notifications про списання сьогодні.
- Cancellation workflow: статус «plan to cancel» з дедлайном → ICS-подія
  «Cancel before» + червона мітка в UI.
- Аналітика витрат по тегах: зведення за категорією за місяць (SVG pie).
- CSV-пресети банків: Revolut / Wise (мапінг колонок за замовчуванням).
- UI: emoji-лого карток підписок, виділена картка total, фільтр paused/active.
- `CHANGELOG.md`, `FUNDING.yml`, favicon + OG-мета, `scripts/smoke.sh`.

## [0.3.0] - 2026-11-04

### Added
- Мультивалютність: конвертація через довідкові курси ECB (дисковий кеш,
  толерантний до відсутності мережі), `?base=` на `/api/summary`.
- Дашборд «worst offenders»: топ-N підписок за monthly-equivalent
  з часткою в межах власної валюти.
- Pause/unpause підписок: видимі у списку, але виключені з підсумків,
  upcoming, ICS та нагадувань.

## [0.2.0] - 2026-10-28

### Added
- Історія цін: кожна зміна amount записується, людяні підсумки
  (`Netflix: 15.49→16.99 (+9.7% за 8 міс)`).
- Cost-per-use: вартість одного використання (`times_used_per_month`).
- Річна проєкція: зведення фактичних списань по календарних місяцях
  + SVG-графік (`/api/projection`, `/api/projection.svg`).

## [0.1.0-alpha] - 2026-10-20

### Added
- CRUD підписок, monthly-equivalent, річний перерахунок.
- Правильні дати: month-end якір (Jan 31 → Feb 28/29 → Mar 31),
  високосні роки, custom-цикли в днях.
- Календар списань 30/60/90 днів, CLI-нагадування (`python -m backend.remind`),
  ICS-експорт (RFC 5545), тріал-трекер.
- CSV-імпорт виписки з авто-детекцією повторюваних платежів
  (7/14/30/31/365 днів ±2) → кандидати на підтвердження.

[Unreleased]: https://github.com/bigpi/subwatch/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/bigpi/subwatch/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bigpi/subwatch/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bigpi/subwatch/compare/v0.1.0-alpha...v0.2.0
[0.1.0-alpha]: https://github.com/bigpi/subwatch/releases/tag/v0.1.0-alpha
