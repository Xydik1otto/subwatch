# Contributing / Внесок

Дякуємо за інтерес до subwatch! Проєкт — local-first і мінімалістичний,
тому кілька простих правил. **English version: [CONTRIBUTING.en.md](CONTRIBUTING.en.md).**

## Як допомогти

- 🐛 Баг-репорти — через [Bug report](.github/ISSUE_TEMPLATE/bug_report.md).
- 💡 Пропозиції — через [Feature request](.github/ISSUE_TEMPLATE/feature_request.md).
- 🔀 Pull request'и — вітаються, дотримуйтесь кроків нижче.

## Правила

1. **Мови спілкування: українська або англійська.** Російську локалізацію
   та російськомовні тексти в коді/документації не додаємо — це політичне
   рішення власника проєкту (див. [i18n](#i18n-українська--англійська)).
2. **Кожна зміна — з тестом.** Новий endpoint або поведінка = новий тест
   у `tests/`. Перед коммітом: `pytest` має бути зеленим повністю.
3. **Кожна фіча — окремий commit** з осмисленим повідомленням.
4. **Privacy-first**: жодних телеметрії, аналітики, зовнішніх викликів
   без явної згоди користувача (виняток — опційні курси валют ECB).
5. **Без секретів у коді**: конфігурація лише через змінні середовища
   (`SUBWATCH_DB`, `SUBWATCH_HOST`, `SUBWATCH_PORT`) з безпечними дефолтами.
6. UI-рядки — через i18n-словники (`static/i18n/uk.json`, `en.json`),
   з перекладом обома мовами. Не хардкодьте текст у шаблонах.
7. A11y: нові інтерактивні елементи отримують `aria-label`,
   кнопки — `type="button"`, таблиці — `scope="col"`.

## Середовище та тести

```bash
pip install -r requirements.txt
pip install -e .          # консольна команда `subwatch`
pytest                    # усі тести мають бути зелені (~233)
pytest tests/test_import.py -q   # один файл
```

- Тести користуються FastAPI `TestClient` (fixture `client` у `conftest.py`)
  і тимчасовою БД — жодних зовнішніх сервісів для запуску не потрібно.
- **Необов'язково, нативний акселератор**: `dotnet 10 SDK` →
  `dotnet publish dotnet/SubRec -c Release -o dotnet/publish`
  (або `SUBWATCH_NATIVE=/шлях/SubRec.exe`; `SUBWATCH_NATIVE=off` — вимкнути).
  Без нього все працює через чистий Python — тести покривають обидва шляхи.
- Стиль: без строгого лінтера, але тримайте код читабельним, типи — у
  сигнатурах, коментарі — там, де «чому», а не «що».

## Архітектура логіки (що де живе)

### Імпорт виписки та евристика `detect_recurring` (backend/csvimport.py)

Конвеєр: сировий текст CSV → `parse_csv()` → `list[Txn]`
(date, description, amount, currency) → `detect_recurring()` → кандидати
на підтвердження (їх бачить користувач у UI; нічого не створюється
автоматично).

**Крок 1 — нормалізація опису** (`normalize_description`): верхній регістр,
усі цифри та розділові знаки замінюються пробілом, пробіли колапсуються.
Кирилиця зберігається (`А-ЯІЇЄҐ`). Тому `NETFLIX.COM 8812` і
`NETFLIX.COM 9931` дають один ключ `NETFLIX COM` і групуються разом —
номери карток/ідентифікатори транзакцій не розбивають групу.

**Крок 2 — групування**: транзакції складаються в словник за
нормалізованим ключем. Групи з менше ніж `MIN_OCCURRENCES = 3` входжень
одразу відкидаються.

**Крок 3 — періодичність**: усередині групи сортуємо за датою, рахуємо
гепи між сусідніми датами і беремо **медіану**. Відомі періоди
`KNOWN_PERIODS = (7, 14, 30, 31, 365)`; обирається найближчий до медіани,
якщо `|геп − період| ≤ DATE_TOLERANCE` (**±2 дні**). Далі кожен окремий
геп має вписуватися в толеранс *хоча б одного* відомого періоду — це
«календарно-чесні» інтервали: місячне списання може мати гепи 28/30/31
дня, і всі вони проходять, а медіана все одно обирає мітку періоду
(30 проти 31). Пропущений місяць (геп 60 днів) групу ламає — і це
свідомо: краще не знайти підписку, ніж запропонувати хибну.

**Крок 4 — суми**: беруться `abs(amount)`; медіана стає сумою кандидата.
Розкид `max − min` у групі має бути `≤ max(0.02, 5% × медіана)`
(`AMOUNT_TOLERANCE = 0.05`) — абсолютний мінімум 2 центи захищає дрібні
суми.

**Крок 5 — валюта та ім'я**: валюта — найчастіша в групі (валюти ніколи
не змішуються), ім'я/опис — найчастіший *первинний* (до нормалізації)
рядок. Наступна дата списання рахується через `schedule.add_months`/
`add_years` (30/31 → monthly, 365 → yearly, інакше custom), фінальний
список кандидатів сортується за спаданням суми.

**Детермінізм — не ламати**: `_most_common()` розв'язує нічиї
«перший зустрінутий», а не порядком `set`/hash. Це умова
**біт-ідентичного паритету** з нативним портом: однаковий вхід має
давати однакових кандидатів у Python і в C#, інакше golden-тести
неможливі.

### Нативний акселератор (backend/native_accel.py + dotnet/SubRec)

`SubRec` — точний порт `parse_csv()` + `detect_recurring()` на C#
(проєкт `dotnet/SubRec`, збірка — `dotnet/README.md`). Коли виконуваний
файл доступний (`SUBWATCH_NATIVE` або дефолт `dotnet/publish/SubRec.exe`),
весь конвеєр CSV → кандидати йде через нього (~2x на виписці 50k рядків);
за відсутності, збою чи `SUBWATCH_NATIVE=off` — тихий fallback на чистий
Python. `/api/import/analyze` використовує акселератор автоматично.

**Правило паритету**: будь-яка зміна евристики (`parse_csv`,
`normalize_description`, `detect_recurring`, сталі `KNOWN_PERIODS`,
`DATE_TOLERANCE`, `AMOUNT_TOLERANCE`, `MIN_OCCURRENCES`) має бути
відзеркалена в `dotnet/SubRec/Detect.cs` і `CsvParse.cs` — інакше
проваляться golden- і fuzz-паритет-тести (`tests/test_native_parity.py`).
Після змін: обидві реалізації + `pytest tests/test_native_parity.py` +
опційно `scripts/benchmark_native.py`.

### Курси валют (backend/rates.py)

Денні довідкові курси **ECB** (`eurofxref-daily.xml`, EUR-based:
«одиниць валюти за 1 EUR»). `fetch_rates()` тягне XML один раз і кешує
на диск з TTL 12 годин (`SUBWATCH_RATES_CACHE` перевизначає шлях).
`get_rates()` ніколи не кидає виключення назовні: мережа недоступна →
застарілий кеш (застарілий курс кращий за відсутність), ні кешу, ні
мережі → `{}`. `convert()` перераховує через EUR-базу. Це **єдиний**
зовнішній виклик у кодовій базі — нові без згоди користувача заборонені.

### ICS-експорт (backend/ics.py)

`build_ics()` віддає RFC 5545-сумісний календар майбутніх списань:
`VCALENDAR 2.0`, рядки через **CRLF**, події на весь день
(`DTSTART;VALUE=DATE`, `DTEND` = наступний день), обов'язкові `UID` і
`DTSTAMP`, екранування `\ ; ,` та переносів рядків у `SUMMARY`/
`DESCRIPTION`. Тести — `tests/test_ics.py`; нові поля в подіях — з
тестом і без порушення екранування.

### Family mode (backend/family.py)

Підписка несе `owner`, `payer` і `share_pct` (частка платника, %).
`family_breakdown()` групує активні підписки за платниками
(`NULL` → «(не вказано)») і рахує для кожного часткові місячні/річні
підсумки: `monthly_equivalent × share_pct/100`. **Валюти ніколи не
змішуються** — підсумки ведуться окремими словниками per currency.
Нові поля сімейного режиму — тільки з тестом у `tests/test_family.py`.

### Cancel assistant (backend/cancel_kb.py)

Статична база знань для топ-20 сервісів підписок: офіційний URL
скасування, ключові слова та покрокові інструкції **обома мовами**
(`steps_uk`, `steps_en`). Жодних мережевих викликів і скрейпінгу —
чисті дані, оновлюються з релізами. `match_service()` знаходить сервіс
за ключовими словами в описі транзакції. Новий сервіс = новий запис у
`SERVICES` з URL, keywords та інструкціями в обох мовах (+ тест у
`tests/test_cancel_kb.py`).

## Як додати банківський пресет (покроково)

Пресет — мапінг колонок CSV-експорту конкретного банку на канонічні
поля (date/description/amount/currency). Існуючі: `revolut`, `wise`.

1. **Візьміть реальний CSV** банку і випишіть точні назви заголовків
   (регістр не важливий; часто в банку кілька колонок з датою —
   «Started Date» і «Completed Date» у Revolut — тоді список alias'ів).
2. **Додайте запис у `PRESETS`** у `backend/csvimport.py`:

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

   Alias'и матчаться без регістру: спершу точний збіг, потім підрядковий.
3. **Нічого більше в коді не потрібно**: `parse_csv(text, preset_name)`
   підхопить пресет, `GET /api/import/presets` віддасть його списком,
   а `POST /api/import/analyze` з `"preset": "monobank"` піде новим
   шляхом.
4. **Тести** в `tests/test_presets.py` за зразком `REVOLUT_CSV`/
   `WISE_CSV`:
   - `/api/import/presets` містить новий пресет (label і ключ);
   - розбір реального шматка виписки (дати у форматі банку, валюта
     колонкою, від'ємні суми) знаходить повторюваний платіж;
   - неспівпадаючий заголовок/невідомий пресет дає 422 або `ValueError`.
5. **Формат дати**: якщо банк пише дати у вигляді, якого немає серед
   `_DATE_FORMATS` (`2024-06-01`, `01.06.2024`, `01/06/2024` (день
   перший перемагає нічию), `06/01/2024`, `01-06-2024`, `2024.06.01`,
   `2024/06/01`, `01 Jun 2024`, `Jun 1, 2024`, плюс відсікання часу від
   ISO-міток) — додайте формат у `_DATE_FORMATS` і окремий тест на нього.
6. `pytest tests/test_presets.py tests/test_import.py` — зелене, і комміт.

## Як додати новий період (розширення 7/14/30/31/365)

Приклад: 90-денний період. Обережно: новий період змінює детекцію для
**всіх** існуючих даних — потрібен паритет і тести.

1. **`KNOWN_PERIODS`** у `backend/csvimport.py` + той самий список у
   `dotnet/SubRec/Detect.cs` (паритет! інакше впадуть golden-тести).
2. **Продумайте неоднозначності** `_pick_period`: медіана обирає
   найближчий період, тож 90 не зашкодить місячним (28–33-денні гепи
   все одно ближчі до 30), але перевірте края: квартал реально
   89–92 дні — ±2 дні покриває 90±2, і кожен окремий геп має
   вписатися в *хоча б один* відомий період. Задокументуйте міркування
   в коментарі.
3. **Мапінг на цикл** у `_next_due()`: 90-денний період не є
   «monthly» — додайте гілку (наприклад, `schedule.add_months(last, 3)`
   з новою cycle-міткою або `custom` з `custom_days=90`).
4. **API-валідація**: `SubscriptionIn.cycle` у `backend/main.py`
   обмежений патерном `^(monthly|yearly|custom)$`. Нова cycle-мітка
   потребує розширення патерну, гілок у `schedule.next_due_date()`,
   `monthly_equivalent()` (коефіцієнт нормалізації до місяця),
   `upcoming_dates()`/`nth_occurrence()`, SQL-сортування в `main.py`
   і перекладів у `static/i18n/uk.json` + `en.json`.
   *Простіший шлях* — мапити новий період на існуючі цикли
   (custom/monthly), тоді API не змінюється.
5. **Тести**: детекція нового періоду (≥3 входжень, реалістичні гепи) у
   `tests/test_import.py`, цикл/еквівалент у `tests/test_schedule.py`,
   паритет Python↔C# у `tests/test_native_parity.py` (додайте випадок
   до golden/fuzz-фікстур).
6. Оновіть згадку періодів у `README.md`/`README.en.md` та CHANGELOG.

## Гілки

- **`master`** — стабільна гілка. Кожен push запускає CI
  (`.github/workflows/tests.yml`, Python 3.12 і 3.13). Невеликі прямі
  коміти — ок; для більшого — фіча-гілка і PR.
- **`mobile/android-ios`** — мобільні оболонки (Capacitor 6): `android/`,
  `ios/`, `mobile/` (splash-екран з адресою сервера), workflows
  `android-build.yml` (APK) та `ios-build.yml` (unsigned, для
  AltStore/Sideloadly). Бекенд-зміни робляться на `master` і потрапляють
  сюди мержем; мобільний код не повинен ламати бекенд — `pytest` зелений
  в обох гілках перед кожним push.

## Pull request'и та коміти

1. Форк/фіча-гілка → зміна **з тестом** → `pytest` повністю зелений.
2. Один логічний фіча = один commit; повідомлення українською або
   англійською у стилі історії проєкту: `Feature: …`, `Fix: …`,
   `Tests: …`, `Docs: …`, `Mobile: …`, `OSS: …`.
3. PR з коротким «що і чому»; CI має бути зеленим перед рев'ю.
4. Приватні дані (реальні виписки, ключі) у тести/фікстури не потрапляють.

## i18n (українська + англійська)

- Всі UI-рядки — у `static/i18n/uk.json` та `en.json`; ключ додається
  **в обидва** словники в одному коміті (тест `tests/test_i18n.py`
  стежить).
- **Російську локалізацію (`ru.json`, `ru-RU`) не додавати ніколи** —
  політичне рішення власника проєкту; hygiene-тести слідкують, щоб вона
  не з'явилася.
- Англійські тексти — природна англійська, українські — природна
  українська; не калькуйте одне з одного.
- A11y-правила (правило 7) застосовуються і до нових i18n-елементів.

## Ліцензія

Відправляючи pull request, ви погоджуєтесь, що ваш внесок ліцензується
під [MIT-ліцензією](LICENSE) проєкту.

## English

The full English version lives in
**[CONTRIBUTING.en.md](CONTRIBUTING.en.md)** — it is a complete mirror
of this document. Quick summary:

1. **Languages: Ukrainian or English.** No Russian localization or
   Russian-language text in code/docs — this is the project owner's
   political decision.
2. **Every change ships with a test.** New endpoint or behavior = new
   test in `tests/`; full `pytest` run must be green before you commit.
3. **One feature = one commit** with a meaningful message.
4. **Privacy-first**: no telemetry, no analytics, no network calls
   without explicit user consent (the optional ECB exchange-rate cache
   is the only exception).
5. **No secrets in code**: configuration happens through environment
   variables (`SUBWATCH_DB`, `SUBWATCH_HOST`, `SUBWATCH_PORT`) with
   safe defaults.

The English mirror covers the same ground in full: the
`detect_recurring` heuristic (normalization, grouping, ±2-day period
tolerance, ±5% amount spread), the C# `SubRec` native-accelerator
parity rule, the ECB rates module, RFC 5545 ICS export, family mode,
the cancel knowledge base, step-by-step recipes for adding a bank
preset and a new period, branch policy (`master` stable vs
`mobile/android-ios`), PR and commit conventions, and i18n rules.
