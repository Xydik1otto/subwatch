# subwatch

![tests](https://github.com/bigpi/subwatch/actions/workflows/tests.yml/badge.svg)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![version](https://img.shields.io/badge/version-1.0.0-orange)

**Українська** | [English](README.en.md)

Local-first трекер підписок. Без хмари, без акаунтів, без телеметрії —
усі дані живуть в одному SQLite-файлі на вашому диску. Python + FastAPI.

## Можливості (v1.0.0)

- CRUD підписок, сортування, monthly-equivalent, річний перерахунок.
- **Правильні дати**: month-end якір (Jan 31 → Feb 28/29 → Mar 31),
  високосні роки, custom-цикли в днях.
- Календар списань 30/60/90 днів, CLI-нагадування, ICS-експорт (RFC 5545),
  тріал-трекер.
- **CSV-імпорт виписки** з авто-детекцією повторюваних платежів
  (періодичність 7/14/30/31/365 днів ±2) → кандидати на підтвердження.
- **Історія цін**: кожна зміна amount записується —
  `Netflix: 15.49→16.99 (+9.7% за 8 міс)`.
- **Cost-per-use**: вартість одного використання підписки.


## Чому це існує

> «Consumers estimate they spend **$86** per month on subscriptions —
> but they actually spend **$219** every month.»
> — West Monroe, national consumer survey (2021)

Підписки спроєктовані так, щоб про них забували:

- **42%** людей забувають про платну підписку (Capterra, 2024).
- **$17/міс** — середні витрати на невикористані підписки (CNET, 2025).
- **44%** користувачів відчувають "subscription fatigue" — втому від
  розростающихся щомісячних списань.
- При цьому тренд ринку йде в протилежний бік: одноразові покупки
  зростають на **+6%/рік**.

Хмарні трекери підписок (Rocket Money, BillShark тощо) вимагають доступу до
банківських даних — це новий ризик заради вирішення проблеми, яку можна
вирішити локально, списком з датами.

## Швидкий старт

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload       # http://127.0.0.1:8000
pytest                                  # математика під тестами
```

### Використання

```bash
# додати підписку (monthly/yearly/custom; custom потребує custom_days)
curl -X POST localhost:8000/api/subscriptions -H 'content-type: application/json' \
  -d '{"name":"Netflix","amount":15.49,"currency":"USD","cycle":"monthly","next_due_date":"2026-12-01"}'

# список (сортування: next_due_date | amount | monthly | name)
curl "localhost:8000/api/subscriptions?sort=next_due_date"

# підсумок: місячний/річний еквівалент по валютах
curl localhost:8000/api/summary

# календар списань на 30/60/90 днів
curl "localhost:8000/api/upcoming?days=90"

# тріали, що закінчуються за 3 дні (список "скасуй або заплатиш")
curl localhost:8000/api/trials

# списання відбулося — перекрутити дату на цикл вперед
curl -X POST localhost:8000/api/subscriptions/1/mark-paid

# cost-per-use: щомісячна вартість / кількість використань
curl -X POST localhost:8000/api/subscriptions -H 'content-type: application/json' \
  -d '{"name":"Gym","amount":30,"cycle":"monthly","next_due_date":"2026-12-01","times_used_per_month":12}'

# експорт ВСІХ майбутніх списань у календар
curl -o subwatch.ics localhost:8000/api/export.ics
```

### Імпорт банківської виписки (CSV)

```bash
# крок 1: авто-детекція повторюваних платежів (періодичність 7/14/30/31/365 днів ±2)
curl -X POST localhost:8000/api/import/analyze -H 'content-type: application/json' \
  -d '{"csv":"date,description,amount\n2026-01-01,NETFLIX.COM,15.49\n2026-02-01,NETFLIX.COM,15.49\n2026-03-01,NETFLIX.COM,15.49"}'

# крок 2: підтвердити знайдених кандидатів -> створення підписок
curl -X POST localhost:8000/api/import/confirm -H 'content-type: application/json' \
  -d '{"candidates":[{"name":"Netflix","amount":15.49,"cycle":"monthly","next_due_date":"2026-04-01"}]}'
```

Парсер розуміє `;`/`,`/tab-розділювачі, українські й англійські заголовки
(`Дата/Опис/Сума`), формати дат `YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`,
десяткові коми (`16,99`), тисячні пробіли (`1 234,56`), мінуси й дужки.

### Нативний акселератор детекції (C#, необов'язково)

Рушій детекції повторюваних платежів має C#-порт (`dotnet/SubRec`, .NET 10
CLI `SubRec.exe`). Якщо exe зібрано, `/api/import/analyze` і
`backend/native_accel.py` виконують весь парсинг + детекцію ним — на
синтетичній виписці **50 000 рядків** це ~**0.4 с** проти ~**0.7 с**
чистого Python (заміри: `python scripts/benchmark_native.py`):

| шлях на 50 000 рядків            | час    |
|----------------------------------|--------|
| Python parse + detect            | 0.74 s |
| SubRec.exe end-to-end            | 0.36 s |
| `/api/import/analyze` (нативний) | 0.39 s |
| Python detect без парсингу       | 0.12 s |

Без exe (або з `SUBWATCH_NATIVE=off`) усе працює на чистому Python —
результати ідентичні на біт (golden/fuzz-тести в `tests/test_native_parity.py`).

```bash
dotnet publish dotnet/SubRec -c Release -o dotnet/publish   # один раз
# SubRec.exe також працює сам: stdin CSV -> stdout JSON
./dotnet/publish/SubRec.exe < statement.csv > candidates.json
```

### Історія цін

```bash
curl localhost:8000/api/subscriptions/1/price-history  # всі точки amount
curl localhost:8000/api/price-changes                  # 'Netflix: 15.49→16.99 (+9.7% за 8 міс)'
```

### CLI-нагадування (локальні, без демона)

```bash
python -m backend.remind --days 7            # що списадуть цього тижня
python -m backend.remind --days 7 --notify   # + локальне вікно-нотифікація (Windows)
```

### Календар

`/api/export.ics` генерує RFC 5545 VCALENDAR з подією на кожне майбутнє
списання (і на кінець тріалу) — імпортуйте в Google Calendar / Outlook /
Apple Calendar, і нагадування прийдуть туди, де ви вже й так дивитесь.

## Що нового у v1.0.0

- **Cancel assistant**: база знань топ-20 сервісів з офіційними лінками
  на скасування (UA/EN) — `curl localhost:8000/api/cancel-assistant`.
- **Цінові алерти**: бейдж 🔔 і мітка «↑ ціна змінилась» при кожній зміні
  суми (`/api/alerts`).
- **Family mode**: хто власник, хто платить і частка
  (`/api/family`).
- **i18n UA/EN**, first-run демо-дані, експорт JSON/CSV, a11y,
  `pip install -e .` з командою `subwatch`, INSTALL.md для не-програміста,
  open-source hygiene (CONTRIBUTING/SECURITY/issue-шаблони).

## Що нового у v0.4.0

- **PWA + web notifications**: manifest і service worker; коли у вас списання
  сьогодні — системне повідомлення прямо в браузері (`GET /api/today`).
- **Cancellation workflow**: `curl -X POST localhost:8000/api/subscriptions/1/plan-cancel -d '{"cancel_deadline":"2026-11-18"}'`
  — статус «plan to cancel»: червона мітка в UI, подія «CANCEL BEFORE»
  в ICS-експорті, окремий список `GET /api/to-cancel`.
- **Аналітика по тегах**: `curl localhost:8000/api/tags` (витрати за категорією
  за місяць) та `curl -o tags.svg localhost:8000/api/tags.svg` — SVG pie-chart.
- **CSV-пресети банків**: `GET /api/import/presets` (revolut, wise) —
  точний мапінг колонок замість вгадування, валюта читається з виписки:
  `POST /api/import/analyze {"csv": "...", "preset": "revolut"}`.
- **UI**: emoji-лого карток, виділена картка «Разом на місяць», фільтр
  Усі / Активні / На паузі.
- `CHANGELOG.md`, `FUNDING.yml`, favicon + OG-мета, `scripts/smoke.sh`.

## Що нового у v0.3.0

- **Мультивалютний summary через курси ECB**: `curl "localhost:8000/api/summary?base=USD"` —
  усі валюти конвертуються через офіційні довідкові курси ЄЦБ
  (кеш на диску, працює офлайн зі свіжого кешу).
- **Worst offenders**: `curl "localhost:8000/api/worst-offenders?limit=5"` —
  топ-5 підписок за місячним еквівалентом з часткою у витратах валюти.
- **Pause**: `curl -X POST localhost:8000/api/subscriptions/1/pause` —
  заморожена підписка видима у списку, але не рахується у totals,
  upcoming, ICS та нагадуваннях; `/unpause` повертає назад.
- **Annual projection**: `curl localhost:8000/api/projection` (JSON по місяцях)
  та `curl -o projection.svg localhost:8000/api/projection.svg` —
  SVG-графік списань на 12 місяців вперед.

## Принципи

1. **100% локальні дані.** SQLite-файл — єдина "база". Немає жодного
   зовнішнього виклику (навіть ціни не потрібні — підписки не котируються).
2. **Правильні дати.** Month-end edge cases обробляються якорем: підписка
   на 31-е лишається "на 31-е" (Jan 31 → Feb 28/29 → Mar 31), а не дрейфує
   на 28-е назавжди. Високосний 29 лютого теж під контролем.
3. **Monthly-equivalent** — чесна нормалізація yearly (÷12) і custom-циклів
   (через 365.25/днів), щоб порівнювати підписки між собою.

## Contributing

Проєкт open-source: читайте [CONTRIBUTING.md](CONTRIBUTING.md) перед
pull request'ом (мови спілкування — українська/англійська; кожна зміна —
з тестом; privacy-first). Безпека — [SECURITY.md](SECURITY.md),
баг-репорти — через шаблони у `.github/ISSUE_TEMPLATE/`.

### Рекомендовані GitHub topics

`subscription-tracker` `local-first` `privacy` `self-hosted` `fastapi`
`python` `sqlite` `personal-finance` `budget` `pwa` `offline-first`
`selfhosted` `money-management`

## Ліцензія

MIT — див. [LICENSE](LICENSE).
