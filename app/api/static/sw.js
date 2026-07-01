const CACHE = 'ka-ai-v1';
const PRECACHE = ['/offline', '/static/manifest.json'];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;

  // Only intercept GET requests over HTTP(S)
  if (request.method !== 'GET' || !request.url.startsWith('http')) return;

  // Navigation requests: network-first, serve offline page on failure
  if (request.mode === 'navigate') {
    e.respondWith(fetch(request).catch(() => caches.match('/offline')));
    return;
  }

  // Static assets: cache-first, populate cache on first fetch
  if (new URL(request.url).pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(request, res.clone()));
          return res;
        });
      })
    );
    return;
  }

  // All other requests (API calls, SSE stream): pass through to network
});

self.addEventListener('push', e => {
  let data = { title: 'kleinanzeigen-ai', body: 'New results found' };
  try { if (e.data) data = e.data.json(); } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(data.title || 'kleinanzeigen-ai', {
      body: data.body || '',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-192.png',
      data: { url: '/dashboard' },
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      const existing = list.find(c => c.url.includes('/dashboard') && 'focus' in c);
      if (existing) return existing.focus();
      return clients.openWindow(e.notification.data.url || '/dashboard');
    })
  );
});
