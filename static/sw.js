var CACHE_NAME = 'vams-cache-v2';
var MOBILE_PREFIXES = ['/m/', '/static/'];
var NAV_URLS_TO_CACHE = ['/m/', '/m/login', '/m/attendance', '/m/tasks', '/m/profile', '/offline/'];

self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function(cache) {
            return cache.addAll(NAV_URLS_TO_CACHE);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(names) {
            return Promise.all(
                names.filter(function(n) { return n !== CACHE_NAME; }).map(function(n) { return caches.delete(n); })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function(event) {
    var req = event.request;
    if (req.method !== 'GET') return;

    // Cache-first for static assets
    if (isStaticAsset(req.url)) {
        event.respondWith(
            caches.match(req).then(function(cached) {
                return cached || fetchAndCache(req);
            })
        );
        return;
    }

    // Network-first with cache fallback for mobile and other pages
    event.respondWith(
        fetch(req).then(function(resp) {
            if (resp && resp.ok) {
                var copy = resp.clone();
                caches.open(CACHE_NAME).then(function(cache) { cache.put(req, copy); });
            }
            return resp;
        }).catch(function() {
            return caches.match(req).then(function(cached) {
                return cached || new Response('Offline', { status: 503 });
            });
        })
    );
});

function isStaticAsset(url) {
    var u = new URL(url);
    return MOBILE_PREFIXES.some(function(p) { return u.pathname.startsWith(p); }) ||
        u.pathname.endsWith('.js') || u.pathname.endsWith('.css') ||
        u.pathname.match(/\.(png|jpg|jpeg|gif|svg|ico|woff2?)$/);
}

function fetchAndCache(req) {
    return fetch(req).then(function(resp) {
        if (resp && resp.ok) {
            var copy = resp.clone();
            caches.open(CACHE_NAME).then(function(cache) { cache.put(req, copy); });
        }
        return resp;
    });
}
