# Contributing / Внесок

**Українська** (нижче) | [English](#english)

Дякуємо за інтерес до subwatch! Проєкт — local-first і мінімалістичний,
тому кілька простих правил.

## Як допомогти

- 🐛 Баг-репорти — через [Bug report](.github/ISSUE_TEMPLATE/bug_report.md).
- 💡 Пропозиції — через [Feature request](.github/ISSUE_TEMPLATE/feature_request.md).
- 🔀 Pull request'и — вітаються, дотримуйтесь кроків нижче.

## Правила

1. **Мови спілкування: українська або англійська.** Російську локалізацію
   та російськомовні тексти в коді/документації не додаємо — це політичне
   рішення власника проєкту.
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

## Розробка

```bash
pip install -r requirements.txt
pip install -e .          # консольна команда `subwatch`
pytest                    # усі тести мають бути зелені
```

Стиль: без строгого лінтера, але тримайте код читабельним, типи — у
сигнатурах, коментарі — там, де «чому», а не «що».

## English

Thanks for your interest in subwatch! A few ground rules:

1. **Languages: Ukrainian or English.** No Russian localization or
   Russian-language text in code/docs — this is the project owner's
   political decision.
2. **Every change ships with a test.** New endpoint or behavior = new test
   in `tests/`; full `pytest` run must be green before you commit.
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

## Development

```bash
pip install -r requirements.txt
pip install -e .          # installs the `subwatch` command
pytest                    # everything must pass
```

By submitting a pull request you agree your contribution is licensed under
the project's [MIT license](LICENSE).
