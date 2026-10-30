const CACHE = "shepard-shell-v29";
const ASSETS = [
  "/", "/styles.css", "/app.js", "/labyrinth-scene.js", "/hand-controls.js", "/file-redirect.js", "/favicon.svg", "/manifest.webmanifest",
  "/assets/shepard-tree.png", "/assets/sheep-sprites.png", "/assets/domain-houses.png",
  "/assets/domain-chapels.png", "/assets/domain-workshops.png", "/assets/domain-towers.png",
  "/assets/domain-keeps.png"
];
self.addEventListener("install", (event) => event.waitUntil(
  caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
));
self.addEventListener("activate", (event) => event.waitUntil(
  caches.keys()
    .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
    .then(() => self.clients.claim())
));
self.addEventListener("fetch", (event) => {
  const pathname = new URL(event.request.url).pathname;
  if (event.request.method !== "GET" || pathname.startsWith("/api/") || pathname.startsWith("/oauth/")) return;
  event.respondWith(fetch(event.request).then((response) => {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(event.request, copy));
    return response;
  }).catch(() => caches.match(event.request)));
});
