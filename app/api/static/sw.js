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
  let data = {
    title: 'kleinanzeigen-ai',
    body: 'New results found',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-72.png',
    tag: 'notification',
    requireInteraction: true,
    data: { url: '/dashboard' },
    actions: [],
    sound: '/static/notification.mp3'
  };
  try {
    if (e.data) {
      const parsed = e.data.json();
      data = { ...data, ...parsed };
    }
  } catch (_) {}

  // Play notification sound (optional)
  if (data.sound && typeof playNotificationSound === 'function') {
    playNotificationSound();
  }

  // Vibration pattern for mobile
  const vibrationPattern = [200, 100, 200];

  e.waitUntil(
    self.registration.showNotification(data.title || 'kleinanzeigen-ai', {
      body: data.body || '',
      icon: data.icon || '/static/icons/icon-192.png',
      badge: data.badge || '/static/icons/icon-72.png',
      tag: data.tag || `search-${Date.now()}`,
      requireInteraction: data.requireInteraction !== false,
      actions: data.actions || [],
      vibrate: vibrationPattern,
      data: {
        url: data.data?.url || '/dashboard',
        searchKeywords: data.data?.searchKeywords,
        taskId: data.data?.taskId,
        resultCount: data.data?.resultCount,
        vibrate: vibrationPattern
      }
    }).then(() => {
      // Trigger vibration when notification is shown
      if (navigator.vibrate && vibrationPattern) {
        navigator.vibrate(vibrationPattern);
      }
      // Notify clients about notification
      self.clients.matchAll().then(clients => {
        clients.forEach(client => {
          client.postMessage({
            type: 'notificationShown',
            data: data
          });
        });
      });
    })
  );
});

self.addEventListener('notificationclick', e => {
  const { action, notification } = e;
  const notifData = notification.data || {};

  if (action === 'dismiss') {
    e.notification.close();
    // Notify clients about dismissal
    self.clients.matchAll().then(clients => {
      clients.forEach(client => {
        client.postMessage({ type: 'notificationDismissed' });
      });
    });
    return;
  }

  const urls = {
    'view-results': `/dashboard#tab-my-results`,
    'open-search': `/dashboard#tab-my-results`,
    default: notifData.url || '/dashboard'
  };

  e.notification.close();

  // Notify clients about click
  self.clients.matchAll().then(clients => {
    clients.forEach(client => {
      client.postMessage({
        type: 'notificationClicked',
        action: action,
        url: urls[action] || urls.default
      });
    });
  });

  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      const existing = list.find(c => c.url.includes('/dashboard') && 'focus' in c);
      const url = urls[action] || urls.default;
      if (existing) {
        existing.navigate(url);
        return existing.focus();
      }
      return clients.openWindow(url);
    })
  );
});

self.addEventListener('notificationclose', e => {
  // Optional: track notification dismissal in analytics
  const { notification } = e;
  if (notification.data?.taskId) {
    // Could send a beacon to track dismissed notifications
  }
});
