import type { CapacitorConfig } from '@capacitor/cli';

/**
 * subwatch — мобільна оболонка (Capacitor).
 *
 * НЕ bundled UI: застосунок підключається до ВЛАСНОГО self-hosted сервера.
 * Адреса сервера вводиться на splash-екрані при першому запуску
 * (mobile/launcher/index.html) і зберігається через @capacitor/preferences.
 *
 * Пуш-нотифікації про сьогоднішні списання — так само, як у PWA: сторінка
 * тягне /api/today і віддає результат «понотифікаційному шару». У браузері
 * цей шар — service worker (static/sw.js, postMessage); у нативній оболонці
 * той самий потік завершується @capacitor/local-notifications з тою самою
 * логікою текстів (заголовок, перші три рядки, «… і ще N»).
 *
 * appId: «subwatch» — валідний Java-пакет без дефісів, тому простір імен
 * і applicationId збігаються: io.github.xydik1otto.subwatch.
 */
const config: CapacitorConfig = {
  appId: 'io.github.xydik1otto.subwatch',
  appName: 'Subwatch',
  webDir: 'mobile/launcher',
  server: {
    androidScheme: 'https',
  },
};

export default config;
