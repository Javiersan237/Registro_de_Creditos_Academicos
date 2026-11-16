/* Renueva TI · Service Worker (FR-22, NFR-11).
   Guarda la app en el celular la primera vez que hay internet, para que el QR
   abra el formulario aunque en el auditorio no haya señal. */
importScripts('/static/js/idb.js');

const CACHE = 'renueva-ti-v2';
const SHELL = ['/app/', '/static/css/renueva.css', '/static/js/alumno.js', '/static/js/idb.js',
  '/manifest.webmanifest', '/static/img/icon-192.png', '/static/img/icon-512.png', '/static/img/isotipo.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function redPrimero(req, respaldo) {
  const cache = await caches.open(CACHE);
  try {
    const resp = await fetch(req);
    if (resp.ok) cache.put(respaldo || req, resp.clone());
    return resp;
  } catch (e) {
    const guardado = await cache.match(respaldo || req, { ignoreSearch: true });
    if (guardado) return guardado;
    throw e;
  }
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // La app (con o sin ?t=token del QR) siempre abre, aunque no haya internet.
  if (req.mode === 'navigate' && url.pathname.startsWith('/app')) {
    e.respondWith(redPrimero(req, '/app/'));
    return;
  }
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') {
    e.respondWith(redPrimero(req));   // con red: siempre la versión nueva; sin red: la guardada
  }
});

// Envío en segundo plano donde el navegador lo permite (Chrome/Android). Riesgo R1 en iPhone.
self.addEventListener('sync', e => {
  if (e.tag === 'rt-sync') e.waitUntil(self.rtSync());
});
