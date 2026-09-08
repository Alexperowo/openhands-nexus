// OpenHands Local PWA Service Worker
// Version: 2.0.0 — cache bypass for patched local assets
// Caching Strategy: Network-First / No stale runtime bundles / Zero offline staleness

const CACHE_NAME = 'openhands-pwa-v2';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Strictly NEVER cache:
  // - Non-GET requests
  // - Agent server / Automation APIs
  // - WebSockets (/sockets)
  // - Voice streaming / Voice Bridge APIs
  // - Server info
  if (
    event.request.method !== 'GET' ||
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/sockets') ||
    url.pathname.startsWith('/voice-api') ||
    url.pathname.startsWith('/voice') ||
    url.pathname.startsWith('/server_info')
  ) {
    return;
  }

  // Network-First with fallback to cache if available.
  // Use cache:'no-cache' so Chrome sends a conditional GET (ETag/Last-Modified)
  // even for assets marked immutable — ensures in-place file patches are visible
  // immediately without requiring the user to clear browser data.
  event.respondWith(
    fetch(event.request, { cache: 'no-cache' })
      .then((networkResponse) => {
        if (
          networkResponse &&
          networkResponse.status === 200 &&
          (url.pathname === '/' ||
           url.pathname.endsWith('.html') ||
           url.pathname.endsWith('.png') ||
           url.pathname.endsWith('.svg') ||
           url.pathname.endsWith('.webmanifest'))
        ) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        if (event.request.mode === 'navigate') {
          const rootCached = await caches.match('/');
          if (rootCached) return rootCached;
        }
        return new Response('Network disconnected', {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'Content-Type': 'text/plain' }
        });
      })
  );
});
