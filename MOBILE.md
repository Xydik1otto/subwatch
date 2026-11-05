# 📱 Мобільні застосунки / Mobile apps

Subwatch — **self-hosted**: мобільна оболонка (Capacitor 6) не містить
власного UI, а підключається до **вашого сервера**. Адреса сервера вводиться
на splash-екрані при першому запуску й зберігається на пристрої.

Subwatch is **self-hosted**: the mobile shell (Capacitor 6) ships no bundled
UI — it connects to **your own server**. You enter the server address on the
splash screen at first launch; it is stored on the device.

Пуш-нотифікації про сьогоднішні списання працюють так само, як у PWA:
застосунок тягне `/api/today` і віддає результат «понотифікаційному шару».
У браузері цей шар — service worker (`static/sw.js`, повідомлення через
`postMessage`); у нативній оболонці — `@capacitor/local-notifications` з тою
самою логікою заголовка і тіла, один раз на добу на сервер.

Charges-today notifications work the same way as in the PWA: the app fetches
`/api/today` and hands the result to a notification layer. In a browser that
layer is the service worker (`static/sw.js`, messages via `postMessage`); in
the native shell it is `@capacitor/local-notifications` with the same
title/body logic, once per day per server.

---

## 🇺🇦 Українською

### Android — sideload APK (безкоштовно)

1. Відкрийте [Releases](https://github.com/xydik1otto/subwatch/releases)
   і скачайте `app-debug.apk` (артефакт збірки CI додається до кожного тега;
   окремі APK зі звичайних пушів лежать у артефактах Actions, 30 днів).
2. Дозвольте «Встановлення невідомих застосунків» для браузера/файлового
   менеджера → відкрийте APK → «Встановити».
3. При першому запуску введіть адресу сервера, напр.
   `http://192.168.1.10:8000`.

APK — debug-збірка: підходить для особистого користування; release-підпис
не потрібен, бо застосунок не публікується в магазині.

### iOS — AltStore / Sideloadly (безкоштовно, re-sign кожні 7 днів)

App Store вимагає Apple Developer ($99/рік) — це не в бюджеті проєкту, тому
збирається **unsigned** `.app` (zip-артефакт у Actions, 30 днів):

1. Скачайте `Subwatch-unsigned.zip` зі сторінки виконання
   [Actions → ios-build](https://github.com/xydik1otto/subwatch/actions/workflows/ios-build.yml).
2. Розпакуйте, отриману папку `App.app` перетягніть у
   [Sideloadly](https://sideloadly.io) або [AltStore](https://altstore.io)
   → підпис вашим безкоштовним Apple ID → встановлення на пристрій.
3. Безкоштовний сертифікат діє 7 днів — перевстановіть/re-sign після
   закінчення строку.

### Нотифікації про сьогоднішні списання

При кожному холодному запуску оболонка (до переходу на сервер) перевіряє
`/api/today` і показує системне повідомлення з тими самими текстами, що й
PWA («Списання сьогодні: …» / список до трьох позицій + «… і ще N»). Один
раз на добу на сервер — повторні запуски не спамлять. Дозвіл на
нотифікації запитується перед першим показом.

### Змінити адресу сервера

На splash-екрані: якщо збережений сервер недоступний, застосунок сам
поверне поле введення з повідомленням про помилку; кнопка «Змінити сервер»
доступна під час підключення. Адреса зберігається через
`@capacitor/preferences`.

### Віддалений доступ: Tailscale (безкоштовно)

Сервер слухає у локальній мережі (дефолт — порт 8000); щоб користуватися
застосунком ззовні:

1. Встановіть [Tailscale](https://tailscale.com) на сервер і на телефон
   (безкоштовний тариф достатній для особистого використання).
2. На сервері: `tailscale up` — пристрій отримає IP `100.x.y.z`.
3. У застосунку введіть `http://100.x.y.z:8000` (або ваш `SUBWATCH_PORT`).
   Аналогічно працює WireGuard / VPN вашого вибору.

> Через Tailscale можна також HTTPS: `tailscale serve` — тоді адреса буде
> `https://<machine>.<tailnet>.ts.net`.

### Збірка локально

```bash
npm install          # @capacitor/* + typescript
npm run cap:android  # або: npx cap sync ios
cd android && ./gradlew assembleDebug   # APK: android/app/build/outputs/apk/debug/
# iOS: needs macOS + Xcode + CocoaPods
cd ../ios/App && pod install && \
  xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -sdk iphoneos -derivedDataPath build CODE_SIGNING_ALLOWED=NO
```

Обмеження: `android/` — minSdk 24 (Android 7.0), targetSdk 35 (Android 16),
єдиний дозвіл — `INTERNET`; `ios/` — deployment target iOS 14.0, у
Info.plist дозволено http (`NSAppTransportSecurity`) для LAN/Tailscale.

---

## 🇬🇧 English

### Android — sideload the APK (free)

1. Open [Releases](https://github.com/xydik1otto/subwatch/releases) and
   download `app-debug.apk` (CI attaches it to every tag; per-push APKs
   live in Actions artifacts, 30-day retention).
2. Allow "Install unknown apps" for your browser/file manager → open the
   APK → Install.
3. On first launch enter your server address, e.g.
   `http://192.168.1.10:8000`.

It is a debug-signed APK — fine for personal use; no store signing required.

### iOS — AltStore / Sideloadly (free, re-sign every 7 days)

The App Store requires Apple Developer ($99/yr) — out of budget for this
project, so CI builds an **unsigned** `.app` (zip artifact in Actions,
30-day retention):

1. Download `Subwatch-unsigned.zip` from an
   [Actions → ios-build](https://github.com/xydik1otto/subwatch/actions/workflows/ios-build.yml)
   run.
2. Unzip it and drop the `App.app` folder into
   [Sideloadly](https://sideloadly.io) or [AltStore](https://altstore.io)
   → sign with your free Apple ID → install on the device.
3. Free certificates expire after 7 days — re-sign/reinstall when they do.

### Charges-today notifications

On every cold start the shell (before handing you over to the server)
checks `/api/today` and shows a system notification with the same texts as
the PWA ("Charge today: …" / up to three lines + "… and N more"). Once per
day per server — repeat launches do not spam. The notification permission
is requested before the first notification.

### Changing the server address

If the saved server is unreachable, the splash screen returns to the
address field with an error message; a "Change server" button is available
while connecting. The address is stored via `@capacitor/preferences`.

### Remote access: Tailscale (free)

The server listens on the local network (default port 8000); to use the
app remotely:

1. Install [Tailscale](https://tailscale.com) on the server and the phone
   (the free tier is enough for personal use).
2. On the server: `tailscale up` — it gets a `100.x.y.z` IP.
3. Enter `http://100.x.y.z:8000` (or your `SUBWATCH_PORT`) in the app.
   WireGuard or any VPN works the same way. For HTTPS: `tailscale serve` →
   `https://<machine>.<tailnet>.ts.net`.

### Building locally

```bash
npm install          # @capacitor/* + typescript
npm run cap:android  # or: npx cap sync ios
cd android && ./gradlew assembleDebug   # APK: android/app/build/outputs/apk/debug/
# iOS: needs macOS + Xcode + CocoaPods
cd ../ios/App && pod install && \
  xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -sdk iphoneos -derivedDataPath build CODE_SIGNING_ALLOWED=NO
```

Constraints: `android/` — minSdk 24 (Android 7.0), targetSdk 35
(Android 16), the single permission is `INTERNET`; `ios/` — deployment
target iOS 14.0, plain http is allowed in Info.plist
(`NSAppTransportSecurity`) for LAN/Tailscale.
