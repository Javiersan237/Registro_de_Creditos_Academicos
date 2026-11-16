/* Renueva TI · almacenamiento local del celular (IndexedDB) y sincronizador.
   Se usa desde la página y desde el Service Worker (FR-22, FR-23, NFR-11).
   Almacenes:
     paquetes   → datos de cada conferencia descargados antes (cuestionario, ventana, padrón en hash)
     pendientes → registros hechos sin internet, en cola de envío
     registros  → registros ya enviados, con su folio y último estado conocido */
(function (g) {
  const NOMBRE = 'renueva-ti', VERSION = 1;
  let dbp = null;

  function abrir() {
    if (dbp) return dbp;
    dbp = new Promise((ok, mal) => {
      const req = indexedDB.open(NOMBRE, VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains('paquetes')) db.createObjectStore('paquetes', { keyPath: 'id' });
        if (!db.objectStoreNames.contains('pendientes')) db.createObjectStore('pendientes', { keyPath: 'uuid' });
        if (!db.objectStoreNames.contains('registros')) db.createObjectStore('registros', { keyPath: 'uuid' });
      };
      req.onsuccess = () => ok(req.result);
      req.onerror = () => mal(req.error);
    });
    return dbp;
  }

  function tx(store, modo, fn) {
    return abrir().then(db => new Promise((ok, mal) => {
      const t = db.transaction(store, modo), s = t.objectStore(store);
      const r = fn(s);
      t.oncomplete = () => ok(r && 'result' in r ? r.result : undefined);
      t.onerror = () => mal(t.error);
    }));
  }

  const rtDB = {
    put: (store, obj) => tx(store, 'readwrite', s => s.put(obj)),
    get: (store, key) => tx(store, 'readonly', s => s.get(key)),
    all: (store) => tx(store, 'readonly', s => s.getAll()),
    del: (store, key) => tx(store, 'readwrite', s => s.delete(key)),
  };

  let sincronizando = false;
  /* Envía la cola. Devuelve la lista de registros que sí llegaron.
     - 200/201: llegó (o ya existía: el servidor es idempotente por uuid) → sale de la cola.
     - 4xx: el servidor lo rechazó con un motivo → sale de la cola y se guarda el motivo.
     - Red caída o 5xx: se queda en la cola para el siguiente intento. */
  async function rtSync() {
    if (sincronizando) return [];
    sincronizando = true;
    const enviados = [];
    try {
      const cola = await rtDB.all('pendientes');
      for (const p of cola) {
        let resp;
        try {
          resp = await fetch('/api/registros', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p.datos)
          });
        } catch (e) { break; }  // sin conexión: se intenta después
        if (resp.status >= 500) break;
        const j = await resp.json().catch(() => ({}));
        if (resp.ok && j.registro) {
          await rtDB.put('registros', Object.assign({ conferencia_id: p.datos.conferencia_id, no_control: p.datos.no_control,
            duplicado: !!j.duplicado }, j.registro, { uuid: p.uuid }));
          enviados.push(j.registro);
        } else {
          await rtDB.put('registros', { uuid: p.uuid, folio: '—', conferencia: p.conferencia, valido: false,
            no_control: p.datos.no_control, conferencia_id: p.datos.conferencia_id,
            estado: 'No se pudo registrar', motivo: j.error || 'El servidor rechazó el registro', paso: 0 });
          enviados.push({ error: j.error });
        }
        await rtDB.del('pendientes', p.uuid);
      }
    } finally { sincronizando = false; }
    return enviados;
  }

  g.rtDB = rtDB;
  g.rtSync = rtSync;
})(typeof self !== 'undefined' ? self : window);
