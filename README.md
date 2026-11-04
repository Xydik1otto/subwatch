# subwatch

Local-first трекер підписок. Без хмари, без акаунтів, без телеметрії —
усі дані живуть в одному SQLite-файлі на вашому диску. Python + FastAPI.

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

# експорт ВСІХ майбутніх списань у календар
curl -o subwatch.ics localhost:8000/api/export.ics
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

## Принципи

1. **100% локальні дані.** SQLite-файл — єдина "база". Немає жодного
   зовнішнього виклику (навіть ціни не потрібні — підписки не котируються).
2. **Правильні дати.** Month-end edge cases обробляються якорем: підписка
   на 31-е лишається "на 31-е" (Jan 31 → Feb 28/29 → Mar 31), а не дрейфує
   на 28-е назавжди. Високосний 29 лютого теж під контролем.
3. **Monthly-equivalent** — чесна нормалізація yearly (÷12) і custom-циклів
   (через 365.25/днів), щоб порівнювати підписки між собою.

## Ліцензія

MIT.
