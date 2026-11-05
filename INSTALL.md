# Встановлення subwatch — покрокова інструкція

Ця інструкція — для людей без досвіду програмування. Усе, що потрібно:
встановити Python, скопіювати проєкт і запустити один файл. Дані
залишаються **на вашому диску** (один SQLite-файл), нічого не відправляється
в інтернет.

---

## Windows 10/11

### 1. Встановіть Python

1. Завантажте Python з https://www.python.org/downloads/ (кнопка «Download Python 3.12+»).
2. Запустіть інсталятор і **обов'язково поставте галочку «Add python.exe to PATH»**.
3. Натисніть «Install Now».

### 2. Отримайте subwatch

```bat
git clone https://github.com/bigpi/subwatch.git
cd subwatch
```

(Немає git? На сторінці репозиторія: зеленa кнопка **Code → Download ZIP**,
розпакуйте архів і відкрийте папку.)

### 3. Запуск

```bat
pip install -r requirements.txt
subwatch
```

Відкрийте в браузері: **http://127.0.0.1:8000**

Або подвійний клік по `start.bat` (див. нижче) — він зробить усе сам.

### 4. Автозапуск (щоб subwatch стартував із Windows)

1. Натисніть `Win + R`, введіть `shell:startup`, Enter.
2. Скопіюйте ярлик `start.bat` у папку, що відкрилась.
3. Тепер subwatch стартує разом із системою і чекатиме на
   http://127.0.0.1:8000 у фоновому режимі.

### start.bat (створіть у корені проєкту, якщо його немає)

```bat
@echo off
cd /d "%~dp0"
python -m backend.serve
```

---

## Linux (Ubuntu/Debian/Fedora)

### 1. Встановіть Python

```bash
sudo apt install python3 python3-pip python3-venv   # Debian/Ubuntu
# sudo dnf install python3 python3-pip              # Fedora
```

### 2. Отримайте subwatch і віртуальне середовище

```bash
git clone https://github.com/bigpi/subwatch.git
cd subwatch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Запуск

```bash
subwatch        # або: python -m backend.serve
```

Відкрийте: **http://127.0.0.1:8000**

### 4. Автозапуск: systemd user unit

Створіть файл `~/.config/systemd/user/subwatch.service`:

```ini
[Unit]
Description=subwatch — local subscription tracker
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/subwatch
ExecStart=%h/subwatch/.venv/bin/python -m backend.serve
Restart=on-failure

[Install]
WantedBy=default.target
```

Увімкніть:

```bash
systemctl --user daemon-reload
systemctl --user enable --now subwatch
systemctl --user status subwatch   # перевірка: active (running)
```

(Що працював і без входу в систему: `sudo loginctl enable-linger $USER`.)

---

## Оновлення

```bash
cd subwatch
git pull
pip install -r requirements.txt
# Windows: перезапустіть start.bat; Linux: systemctl --user restart subwatch
```

Ваші дані (`subwatch.db`) не зачіпаються оновленнями — нові версії
автоматично мігрують схему при першому запуску.

## Де живуть дані

- За замовчуванням: файл `subwatch.db` у корені проєкту.
- Інше місце: змінна середовища `SUBWATCH_DB` (шлях до файлу).
- Порт/хост: `SUBWATCH_PORT` (дефолт 8000), `SUBWATCH_HOST` (дефолт 127.0.0.1).

## Резервна копія

Достатньо скопіювати `subwatch.db` у безпечне місце. Або в інтерфейсі:
**Експорт JSON / Експорт CSV** — повний зріз даних одним кліком.

## Часті проблеми

| Симптом | Рішення |
|---|---|
| `'python' не є внутрішньою або зовнішньою командою` | перевстановіть Python із галочкою «Add to PATH» |
| Порт 8000 зайнятий | `SUBWATCH_PORT=8080 subwatch` (Windows: `set SUBWATCH_PORT=8080`) |
| Сторінка не відкривається | перевірте, що в консолі є «Uvicorn running on http://127.0.0.1:8000» |
| Курси валют не завантажуються | це нормально офлайн — працює кеш; без `?base=` конвертація не потрібна |
