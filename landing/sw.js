/* Frugl landing service worker.
   - Navigations / HTML: NETWORK-FIRST (users always get fresh content after a deploy;
     fall back to cache when offline).
   - Other same-origin GET assets (icons, etc.): cache-first.
   - Never touches cross-origin (form endpoint, share links) or non-GET. */
const CACHE = "frugl-landing-v3";
const SHELL = ["./", "./index.html", "./manifest.json", "./icons/icon-192.png", "./icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  const isNav = req.mode === "navigate" || req.destination === "document";
  if (isNav) {
    // network-first: fresh HTML when online, cached shell when offline
    e.respondWith(
      fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return resp;
      }).catch(() => caches.match(req).then((r) => r || caches.match("./")))
    );
  } else {
    // cache-first for static assets
    e.respondWith(
      caches.match(req).then((cached) =>
        cached ||
        fetch(req).then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return resp;
        })
      )
    );
  }
});
