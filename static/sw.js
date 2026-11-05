/* subwatch service worker: web notifications про списання сьогодні.
 * Page fetches /api/today and posts {type:'charges-today', items:[...]} here;
 * the SW shows a system notification (no push server, no cloud). */
self.addEventListener('install', (e) => self.skipWaiting());

self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('message', (e) => {
  const data = e.data || {};
  if (data.type !== 'charges-today') return;
  const items = data.items || [];
  if (!items.length) return;
  const lines = items.map((s) => `${s.name} — ${s.amount.toFixed(2)} ${s.currency}`);
  const body = lines.length <= 3 ? lines.join('\n')
    : lines.slice(0, 3).join('\n') + `\n… і ще ${lines.length - 3}`;
  const title = items.length === 1
    ? `Списання сьогодні: ${items[0].name}`
    : `Списань сьогодні: ${items.length}`;
  self.registration.showNotification(title, {
    body,
    icon: '/static/favicon.svg',
    badge: '/static/favicon.svg',
    tag: 'subwatch-charges-today',
  });
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window' }).then((cs) => {
    for (const c of cs) if ('focus' in c) return c.focus();
    return self.clients.openWindow('/');
  }));
});
