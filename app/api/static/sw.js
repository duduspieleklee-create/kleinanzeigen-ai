const CACHE = 'ka-ai-v3';
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

// Navigation requests: network-first, offline page only after a retry.
// A single failed fetch does NOT mean the user is offline: switching between
// wifi and cellular, waking from sleep, or the server restarting during a
// deploy all reject the first attempt while the connection is actually fine.
async function navigate(request) {
  try {
    return await fetch(request);
  } catch (_) {
    try {
      return await fetch(request);
    } catch (_) {
      return (await caches.match('/offline')) || Response.error();
    }
  }
}

// Static assets: serve from cache, refresh the cache in the background so
// updated CSS/JS is picked up on the next load instead of being stale forever.
async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);
  const network = fetch(request).then(res => {
    if (res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(request, copy));
    }
    return res;
  });
  if (cached) {
    network.catch(() => {});
    return cached;
  }
  return network;
}

self.addEventListener('fetch', e => {
  const { request } = e;

  // Only intercept GET requests over HTTP(S)
  if (request.method !== 'GET' || !request.url.startsWith('http')) return;

  if (request.mode === 'navigate') {
    e.respondWith(navigate(request));
    return;
  }

  if (new URL(request.url).pathname.startsWith('/static/')) {
    e.respondWith(staleWhileRevalidate(request));
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
    actions: []
  };
  try {
    if (e.data) {
      const parsed = e.data.json();
      data = { ...data, ...parsed };
    }
  } catch (_) {}

  // Vibration pattern for mobile
  const vibrationPattern = [200, 100, 200];

  e.waitUntil(
    self.registration.showNotification(data.title || 'kleinanzeigen-ai', {
      body: data.body || '',
      icon: data.icon || '/static/icons/icon-192.png',
      badge: data.badge || '/static/icons/icon-72.png',
      image: data.image || undefined,
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
