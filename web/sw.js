// Service worker: app shell works offline; API responses fall back to the last good copy.
const VERSION = 'v1';
const SHELL_CACHE = `stocklens-shell-${VERSION}`;
const API_CACHE = `stocklens-api-${VERSION}`;
const SHELL = [
  './', 'index.html', 'styles.css', 'manifest.webmanifest', 'icons/icon.svg', 'icons/icon-192.png',
  'js/app.js', 'js/api.js', 'js/store.js', 'js/router.js', 'js/ui.js', 'js/charts.js',
  'js/pages/home.js', 'js/pages/analysis.js', 'js/pages/screener.js', 'js/pages/compare.js',
  'js/pages/portfolio.js', 'js/pages/watchlist.js',
  'vendor/vega.min.js', 'vendor/vega-lite.min.js', 'vendor/vega-embed.min.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL_CACHE).then((c) => Promise.all(
    SHELL.map((u) => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => ![SHELL_CACHE, API_CACHE].includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/health') return;
    // Network first; when offline serve the last successful response.
    e.respondWith(fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(API_CACHE).then((c) => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || new Response(
      JSON.stringify({ detail: 'You are offline and this data has not been loaded before.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }))));
    return;
  }

  // Static files: serve the cached copy immediately, refresh it in the background.
  e.respondWith(caches.open(SHELL_CACHE).then((cache) => cache.match(req).then((hit) => {
    const fresh = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => hit);
    return hit || fresh;
  })));
});
