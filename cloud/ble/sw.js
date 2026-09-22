const CACHE_NAME = 'dogi-pwa-v2'; // Bumped version to force cache update

const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/style.css',
  '/manifest.json',
  '/static/dogi_icon_192.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // 1. Fetch manifest.json explicitly with the Pinggy bypass header
      try {
        const manifestReq = new Request('/manifest.json', {
          headers: { 'X-Pinggy-No-Screen': 'true' }
        });
        const manifestRes = await fetch(manifestReq);
        if (manifestRes.ok) {
          await cache.put('/manifest.json', manifestRes);
        }
      } catch (err) {
        console.error('Failed to pre-cache manifest with header:', err);
      }

      // 2. Cache remaining static assets
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Intercept any request for manifest.json and serve the cached version or add bypass header
  if (url.pathname.endsWith('/manifest.json')) {
    event.respondWith(
      caches.match('/manifest.json').then((cachedManifest) => {
        if (cachedManifest) {
          return cachedManifest;
        }
        return fetch(event.request, {
          headers: { 'X-Pinggy-No-Screen': 'true' }
        });
      })
    );
    return;
  }

  // Default caching behavior for all other requests
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).catch(() => {
        if (event.request.mode === 'navigate') {
          return caches.match('/index.html');
        }
      });
    })
  );
});