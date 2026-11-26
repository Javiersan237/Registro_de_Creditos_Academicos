/* Renueva TI · Servicio de avisos por WhatsApp (FR-14, FR-27).
   Usa whatsapp-web.js: vincula un número de PRUEBAS como «dispositivo» (igual que WhatsApp Web).
   Biblioteca no oficial → riesgo de bloqueo del número (riesgo R4 del E3). El correo es el canal garantizado.

   Endpoints (solo escucha en 127.0.0.1; Django le habla con un token):
     GET  /qr      → página con el QR para vincular el número (abrir en el navegador de la laptop)
     GET  /estado  → { listo, detalle }
     POST /enviar  → { telefono: "4881234567", mensaje: "..." } */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const QRCode = require('qrcode');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

// Lee ../.env (mismo archivo que usa Django); en la versión del salón, el de la carpeta de datos (RENUEVA_DATOS)
const envPath = process.env.RENUEVA_DATOS ? path.join(process.env.RENUEVA_DATOS, '.env') : path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
  for (const linea of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const m = linea.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
}
const PUERTO = parseInt(process.env.WHATSAPP_PORT || '3001', 10);
const TOKEN = process.env.WHATSAPP_TOKEN || '';
// Sin token propio no arranca: con uno conocido, cualquier programa de la computadora podría mandar mensajes.
if (!TOKEN || TOKEN.startsWith('cambia-')) {
  console.error('[WhatsApp] Falta WHATSAPP_TOKEN en .env (o sigue con el valor de ejemplo). Pon uno propio y largo.');
  process.exit(1);
}
const LADA = process.env.WHATSAPP_LADA_PAIS || '52';   // México

// La sesión va en una ruta sin acentos ni espacios (Chrome falla con rutas como «N°5»).
const SESION = process.env.WHATSAPP_SESION_DIR ||
  path.join(process.env.LOCALAPPDATA || require('node:os').homedir(), 'renueva-ti-whatsapp');
process.on('unhandledRejection', e => console.error('[WhatsApp] Error no controlado:', e && e.message));

let listo = false, detalle = 'Iniciando…', qrActual = null;

// Usa el Chrome o Edge que ya tiene la computadora (o WHATSAPP_CHROME_PATH en .env).
const candidatos = [process.env.WHATSAPP_CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].filter(Boolean);
const navegador = candidatos.find(p => fs.existsSync(p));
console.log('[WhatsApp] Navegador: ' + (navegador || 'el de puppeteer'));

// 24 nov 2026: desde WhatsApp Web 2.3000.1055852612 las sesiones NUEVAS ya no reciben QR con whatsapp-web.js 1.34.8
// (issue #201988, abierto). Para vincular la primera vez se usa una copia revisada de una versión anterior, guardada en
// wa_version/ (tomada de wppconnect-team/wa-version; solo carga scripts de web.whatsapp.com y static.whatsapp.net;
// huella en wa_version/SHA256.txt). Con sesión ya guardada se usa WhatsApp Web normal. WHATSAPP_WEB_VERSION=no la desactiva.
const VERSION_VINCULAR = process.env.WHATSAPP_WEB_VERSION || '2.3000.1055837054-alpha';
const MARCA = path.join(SESION, '.vinculado');   // se escribe al quedar conectado; se borra si se cierra la sesión
const haySesion = fs.existsSync(MARCA);
const usarCopia = !haySesion && VERSION_VINCULAR !== 'no' &&
  fs.existsSync(path.join(__dirname, 'wa_version', VERSION_VINCULAR + '.html'));
console.log('[WhatsApp] ' + (usarCopia ? 'Primera vinculación con la versión guardada ' + VERSION_VINCULAR : 'WhatsApp Web normal'));

const cliente = new Client({
  authStrategy: new LocalAuth({ dataPath: SESION }),
  puppeteer: { headless: true, executablePath: navegador, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
  // Sin caché de la versión de WhatsApp Web: una copia vieja en .wwebjs_cache era la causa del atasco en «Autenticado».
  webVersionCache: usarCopia ? { type: 'local', path: path.join(__dirname, 'wa_version'), strict: true } : { type: 'none' },
  webVersion: usarCopia ? VERSION_VINCULAR : undefined,
  // Una laptop recién instalada descarga WhatsApp Web completo la primera vez: 30 s (valor por defecto) no alcanzan.
  authTimeoutMs: 180000,
});

cliente.on('qr', async qr => {
  listo = false; esperandoQR = true; clearTimeout(guardian); detalle = 'Esperando que escanees el QR (abre http://127.0.0.1:' + PUERTO + '/qr)';
  qrActual = await QRCode.toDataURL(qr, { width: 320, margin: 2 });
  console.log('[WhatsApp] ' + detalle);
});
// D-15: al reconectar con la sesión guardada, whatsapp-web.js a veces se queda en «Autenticado» (o cargando) y el
// evento «ready» nunca llega. Guardián: si en 60 s no queda listo, reinicia el cliente con la misma sesión (sin pedir
// QR). Ya no se rinde: después de 5 intentos sigue probando cada 3 minutos. Mientras espera un QR no hace nada.
let guardian = null, reintentos = 0, reiniciando = false, esperandoQR = false;
async function reiniciarCliente(motivo) {
  if (reiniciando) return;
  reiniciando = true; listo = false;
  cliente.info = undefined;     // la de la sesión anterior engañaba al guardián («conectado» sin escuchas)
  reintentos++;
  detalle = `${motivo}; reintento ${reintentos}…`;
  console.warn('[WhatsApp] ' + detalle);
  try { await cliente.destroy(); } catch (e) { }
  try { fs.rmSync(path.join(__dirname, '.wwebjs_cache'), { recursive: true, force: true }); } catch (e) { }
  reiniciando = false;
  vigilarListo();
  cliente.initialize().catch(e => { detalle = 'No se pudo reiniciar: ' + e.message; console.error(e); });
}
/* 24 nov 2026: «Conectado sin aviso ready» = podía ENVIAR pero no RECIBIR. whatsapp-web.js pone sus escuchas de
   mensajes (attachEventListeners) justo antes de emitir «ready»; si «ready» no llega, esas escuchas no existen.
   Ahora una marca dentro de la página (window.__escuchasListas) dice si las escuchas están puestas. Se escribe al
   llegar «ready» o al completarlas a mano, y desaparece sola si la página de WhatsApp Web se recarga. */
async function enPagina(fn, porDefecto) {
  try { return await Promise.race([cliente.pupPage.evaluate(fn), new Promise(r => setTimeout(() => r(porDefecto), 10000))]); }
  catch (e) { return porDefecto; }
}
const escuchando = () => enPagina(() => !!window.__escuchasListas, false);
const marcarEscucha = () => enPagina(() => { window.__escuchasListas = Date.now(); return true; }, false);
let reparando = false;
async function completarEscuchas() {
  // Conectado pero sin escuchas: se termina lo que faltó (info + escuchas) sin reiniciar. Solo si las utilidades
  // de whatsapp-web.js (window.WWebJS) ya están cargadas; si no, hay que reiniciar.
  if (reparando || reiniciando) return false;
  reparando = true;
  try {
    if (!(await enPagina(() => typeof window.WWebJS !== 'undefined', false))) return false;
    const datos = await enPagina(() => ({
      ...window.require('WAWebConnModel').Conn.serialize(),
      wid: window.require('WAWebUserPrefsMeUser').getMaybeMePnUser() || window.require('WAWebUserPrefsMeUser').getMaybeMeLidUser(),
    }), null);
    if (!datos || !datos.wid) return false;
    const ClientInfo = require('whatsapp-web.js/src/structures/ClientInfo');
    const InterfaceController = require('whatsapp-web.js/src/util/InterfaceController');
    cliente.info = new ClientInfo(cliente, datos);
    if (!cliente.interface) cliente.interface = new InterfaceController(cliente);
    await cliente.attachEventListeners();
    await marcarEscucha();
    console.log('[WhatsApp] Escuchas de mensajes completadas sin aviso «ready»');
    return true;
  } catch (e) {
    console.error('[WhatsApp] No se pudieron completar las escuchas:', e && e.message);
    return false;
  } finally { reparando = false; }
}
function vigilarListo() {
  clearTimeout(guardian);
  const espera = reintentos < 5 ? 60000 : 180000;
  guardian = setTimeout(async () => {
    if (listo || esperandoQR) return;
    // Ya conectado pero faltó «ready»: se completan las escuchas; solo así se da por listo (enviar Y recibir).
    let estado = null;
    try { estado = await Promise.race([cliente.getState(), new Promise(r => setTimeout(() => r(null), 15000))]); } catch (e) { }
    if (estado === 'CONNECTED' && ((await escuchando()) || (await completarEscuchas()))) {
      listo = true; reintentos = 0; qrActual = null;
      try { fs.mkdirSync(SESION, { recursive: true }); fs.writeFileSync(MARCA, new Date().toISOString()); } catch (e) { }
      detalle = 'Conectado como ' + (cliente.info?.wid?.user || 'número vinculado') + ' (escuchas completadas sin «ready»)';
      console.log('[WhatsApp] ' + detalle);
      return;
    }
    reiniciarCliente(estado === 'CONNECTED' ? 'Conectado pero sin recibir mensajes' : 'No terminó de cargar');
  }, espera);
}
// Chequeo de salud: cada 2 min pregunta el estado; si dos veces seguidas no está CONECTADO, reinicia.
let fallosSalud = 0;
setInterval(async () => {
  if (!listo || reiniciando) return;
  let estado = null;
  try { estado = await Promise.race([cliente.getState(), new Promise(r => setTimeout(() => r('SIN RESPUESTA'), 20000))]); }
  catch (e) { estado = 'ERROR ' + e.message; }
  if (estado === 'CONNECTED') {
    fallosSalud = 0;
    // Conectado no basta: si la página se recargó o las escuchas faltan, ya no llegarían mensajes.
    if (!(await escuchando())) {
      console.warn('[WhatsApp] Chequeo de salud: conectado pero sin escuchas de mensajes');
      if (!(await completarEscuchas())) reiniciarCliente('Conectado pero sin recibir mensajes');
    }
    return;
  }
  fallosSalud++;
  console.warn(`[WhatsApp] Chequeo de salud: ${estado} (${fallosSalud}/2)`);
  if (fallosSalud >= 2) { fallosSalud = 0; reiniciarCliente('Conexión perdida (' + estado + ')'); }
}, 120000);
cliente.on('loading_screen', (pct, msg) => console.log(`[WhatsApp] Cargando ${pct}% ${msg || ''}`));
cliente.on('authenticated', () => { esperandoQR = false; detalle = 'Autenticado, cargando chats…'; console.log('[WhatsApp] Autenticado'); vigilarListo(); });
cliente.on('ready', () => {
  clearTimeout(guardian); reintentos = 0; fallosSalud = 0;
  try { fs.mkdirSync(SESION, { recursive: true }); fs.writeFileSync(MARCA, new Date().toISOString()); } catch (e) { }
  listo = true; qrActual = null;
  detalle = 'Conectado como ' + (cliente.info?.wid?.user || 'número vinculado');
  console.log('[WhatsApp] ' + detalle);
  marcarEscucha();      // «ready» llega justo después de que whatsapp-web.js puso sus escuchas
});
cliente.on('auth_failure', m => { try { fs.rmSync(MARCA, { force: true }); } catch (e) { } listo = false; detalle = 'Falló la autenticación: ' + m; console.error('[WhatsApp] ' + detalle); });
cliente.on('disconnected', r => {
  listo = false; console.warn('[WhatsApp] Desconectado: ' + r);
  if (r === 'LOGOUT') { try { fs.rmSync(MARCA, { force: true }); } catch (e) { } }
  setTimeout(() => reiniciarCliente('Desconectado (' + r + ')'), 5000);
});


// Extensión local opcional, FUERA del repositorio (herramientas personales de quien opera la computadora).
// WHATSAPP_EXTENSION=<ruta a un .js> que exporta (ctx) => {}: puede escuchar eventos del cliente y agregar rutas
// (protegidas con el mismo token). Sin la variable no se carga nada.
const rutasExtra = {};
if (process.env.WHATSAPP_EXTENSION) {
  try {
    require(path.resolve(process.env.WHATSAPP_EXTENSION))({
      cliente, rutas: rutasExtra, responder, LADA, MessageMedia, enPagina, escuchando, completarEscuchas,
      estaListo: () => listo, detalle: () => detalle,
    });
    console.log('[WhatsApp] Extensión local cargada: ' + process.env.WHATSAPP_EXTENSION);
  } catch (e) { console.error('[WhatsApp] No se pudo cargar la extensión local:', e.message); }
}

async function enviar(telefono, mensaje) {
  const digitos = String(telefono || '').replace(/\D/g, '');
  if (digitos.length !== 10) throw Object.assign(new Error('El teléfono debe tener 10 dígitos'), { status: 400 });
  // getNumberId resuelve el formato correcto (en México a veces es 521 + número)
  const id = await cliente.getNumberId(LADA + digitos);
  if (!id) throw Object.assign(new Error('Ese número no tiene WhatsApp'), { status: 404 });
  const msg = await cliente.sendMessage(id._serialized, mensaje);
  return msg.id?.id;
}

function responder(res, status, obj) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(obj));
}

const servidor = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/qr') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="5">
      <title>Vincular WhatsApp · TecNM Matehuala</title>
      <body style="font-family:Arial;background:#1B396A;color:#fff;text-align:center;padding:30px">
      <h2>Registro de créditos · Vincular WhatsApp</h2>
      ${listo ? '<p style="font-size:20px">✔ ' + detalle + '</p>'
        : qrActual ? `<p>En el celular que enviará los avisos: WhatsApp → Dispositivos vinculados → Vincular un dispositivo</p>
            <img src="${qrActual}" style="background:#fff;padding:10px;border-radius:12px">`
          : '<p>' + detalle + '</p>'}
      <p style="color:#B9C6DA">La página se actualiza sola cada 5 segundos.</p></body>`);
    return;
  }
  if (req.method === 'GET' && req.url === '/qr.json') {   // para el lanzador del salón (solo escucha en 127.0.0.1)
    const n = listo ? String(cliente.info?.wid?.user || '') : '';
    // Solo se muestra enmascarado: 52 488 *** **33
    const numero = n.length >= 6 ? n.slice(0, n.length - 7) + ' ' + n.slice(-7, -4) + ' *** **' + n.slice(-2) : '';
    return responder(res, 200, { listo, detalle, numero, qr: listo ? null : qrActual });
  }
  if (req.headers['x-token'] !== TOKEN) return responder(res, 401, { ok: false, error: 'Token inválido' });
  if (req.method === 'GET' && req.url === '/estado') return responder(res, 200, { listo, detalle });
  const extra = rutasExtra[req.method + ' ' + req.url];
  if (extra) return extra(req, res);
  if (req.method === 'POST' && req.url === '/apagar') {   // cierre ordenado: guarda la sesión antes de salir
    responder(res, 200, { ok: true });
    console.log('[WhatsApp] Apagando de forma ordenada…');
    cliente.destroy().catch(() => { }).finally(() => process.exit(0));
    return;
  }
  if (req.method === 'POST' && req.url === '/cerrar_sesion') {   // cambiar de número: desvincula de verdad el dispositivo
    responder(res, 200, { ok: true });
    console.log('[WhatsApp] Cerrando la sesión (cambio de número)…');
    try { fs.rmSync(MARCA, { force: true }); } catch (e) { }
    Promise.race([cliente.logout(), new Promise(r => setTimeout(r, 15000))]).catch(() => { })
      .finally(() => cliente.destroy().catch(() => { }).finally(() => process.exit(0)));
    return;
  }
  if (req.method === 'POST' && req.url === '/enviar') {
    let cuerpo = '';
    req.on('data', c => { cuerpo += c; if (cuerpo.length > 20000) req.destroy(); });
    req.on('end', async () => {
      if (!listo) return responder(res, 503, { ok: false, error: 'WhatsApp no está conectado: ' + detalle });
      try {
        const { telefono, mensaje } = JSON.parse(cuerpo || '{}');
        const id = await enviar(telefono, mensaje);
        console.log('[WhatsApp] Enviado a ***' + String(telefono).slice(-4));
        responder(res, 200, { ok: true, id });
      } catch (e) {
        console.error('[WhatsApp] Error:', e.message);
        responder(res, e.status || 500, { ok: false, error: e.message });
      }
    });
    return;
  }
  responder(res, 404, { ok: false, error: 'Ruta no encontrada' });
});

servidor.listen(PUERTO, '127.0.0.1', () => console.log(`[WhatsApp] Servicio en http://127.0.0.1:${PUERTO} (QR en /qr)`));
vigilarListo();   // cubre también el atasco ANTES de «Autenticado»
cliente.initialize().catch(e => { detalle = 'No se pudo iniciar el navegador: ' + e.message; console.error(e); });
