self.addEventListener('install', (event) => {
    // Force the waiting service worker to become the active service worker.
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Tell the active service worker to take control of the page immediately.
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Simple passthrough. Essential for PWA installability requirements.
    event.respondWith(fetch(event.request));
});
