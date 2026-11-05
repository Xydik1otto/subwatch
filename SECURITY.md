# Security Policy / Політика безпеки

**Українська** (нижче) | [English](#english)

## Українська

### Архітектура безпеки

subwatch — локальний застосунок: сервер слухає лише `127.0.0.1`
(або `SUBWATCH_HOST`, який ви налаштували), дані живуть в одному
SQLite-файлі. Жодних акаунтів, жодної телеметрії, жодних секретів у коді.

### Що НЕ є вразливістю

- «Дані зберігаються у відкритому SQLite» — це свідомий дизайн;
  захист файлу — справа ОС (шифрування диска, права доступу).
- Відсутність автентифікації на `127.0.0.1` — застосунок задуманий
  для одного локального користувача. Не виставляйте його в мережу
  без зворотного проксі з автентифікацією.
- Вихідні HTTP-запити тільки до ECB (статистика курсів) і тільки при
  явному `?base=` — інших мережевих викликів немає.

### Як повідомити про вразливість

- **Не створюйте публічний issue** для експлуатованої вразливості.
- Напишіть на email власника репозиторія (див. профіль GitHub) або
  використайте приватне повідомлення GitHub («Report a vulnerability»
  у вкладці Security).
- Опис: кроки відтворення, вплив, версія. Відповідь — протягом 7 днів.

### Підтримувані версії

| Версія | Підтримка |
|--------|-----------|
| 1.0.x  | ✅ |

## English

### Security architecture

subwatch is a local application: the server listens on `127.0.0.1`
(or your configured `SUBWATCH_HOST`) and all data lives in a single
SQLite file. No accounts, no telemetry, no secrets in code.

### What is NOT a vulnerability

- "Data is stored in a plain SQLite file" — deliberate design; protect the
  file with OS-level measures (disk encryption, file permissions).
- No authentication on `127.0.0.1` — the app is designed for a single local
  user. Do not expose it to a network without an authenticating reverse proxy.
- Outbound HTTP requests go only to ECB (exchange rates) and only when you
  explicitly pass `?base=` — there are no other network calls.

### Reporting a vulnerability

- **Do not open a public issue** for an exploitable vulnerability.
- Email the repository owner (see the GitHub profile) or use GitHub's
  private "Report a vulnerability" flow in the Security tab.
- Include reproduction steps, impact, and version. Expect a reply within 7 days.

### Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ |
