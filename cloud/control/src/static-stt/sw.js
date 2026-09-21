const CACHE_NAME = 'stt-pwa-v1';

// Add all local assets your PWA needs to run offline
const ASSETS_TO_CACHE = [
  '/',
  '/master.html',
  '/manifest.json',
  '/static/manifest.json',
  '/static/master.html'
  // Add any local JS or CSS scripts here (e.g., '/static/app.js')
];

// 1. Install Event: Download and cache all app resources locally
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Caching local app shell');
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

// 2. Activate Event: Clean up old caches if updated
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch Event: Serve from local device cache first, fallback to network
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse; // Return locally cached copy immediately
      }
      return fetch(event.request).catch(() => {
        // Fallback for navigation requests if network fails and cache misses
        if (event.request.mode === 'navigate') {
          return caches.match('/master.html');
        }
      });
    })
  );
});