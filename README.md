# subwatch

![tests](https://github.com/bigpi/subwatch/actions/workflows/tests.yml/badge.svg)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![version](https://img.shields.io/badge/version-0.3.0-orange)

Local-first трекер підписок. Без хмари, без акаунтів, без телеметрії —
усі дані живуть в одному SQLite-файлі на вашому диску. Python + FastAPI.

## Можливості (v0.1.0-alpha)

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


## Проблема

Підписки спроєктовані так, щоб про них забували:

- **42%** людей забувають про платну підписку (Capterra).
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

## Ліцензія

MIT — див. [LICENSE](LICENSE).
