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
const { Client, LocalAuth } = require('whatsapp-web.js');

// Lee ../.env (mismo archivo que usa Django)
const envPath = path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
  for (const linea of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const m = linea.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
}
const PUERTO = parseInt(process.env.WHATSAPP_PORT || '3001', 10);
const TOKEN = process.env.WHATSAPP_TOKEN || 'cambia-este-token';
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

const cliente = new Client({
  authStrategy: new LocalAuth({ dataPath: SESION }),
  puppeteer: { headless: true, executablePath: navegador, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
});

cliente.on('qr', async qr => {
  listo = false; detalle = 'Esperando que escanees el QR (abre http://127.0.0.1:' + PUERTO + '/qr)';
  qrActual = await QRCode.toDataURL(qr, { width: 320, margin: 2 });
  console.log('[WhatsApp] ' + detalle);
});
// D-15: al reconectar con la sesión guardada, whatsapp-web.js a veces se queda en «Autenticado» y el evento
// «ready» nunca llega (falla conocida de la librería en 2026). Guardián: si en 90 s no queda listo, se reinicia
// el cliente con la misma sesión (sin pedir QR), hasta 5 veces.
let guardian = null, reintentos = 0;
function vigilarListo() {
  clearTimeout(guardian);
  guardian = setTimeout(async () => {
    if (listo || reintentos >= 5) return;
    reintentos++;
    detalle = `No terminó de cargar; reintento ${reintentos} de 5…`;
    console.warn('[WhatsApp] ' + detalle);
    try { await cliente.destroy(); } catch (e) { }
    cliente.initialize().catch(e => { detalle = 'No se pudo reiniciar: ' + e.message; console.error(e); });
  }, 90000);
}
cliente.on('loading_screen', (pct, msg) => console.log(`[WhatsApp] Cargando ${pct}% ${msg || ''}`));
cliente.on('authenticated', () => { detalle = 'Autenticado, cargando chats…'; console.log('[WhatsApp] Autenticado'); vigilarListo(); });
cliente.on('ready', () => {
  clearTimeout(guardian); reintentos = 0;
  listo = true; qrActual = null;
  detalle = 'Conectado como ' + (cliente.info?.wid?.user || 'número vinculado');
  console.log('[WhatsApp] ' + detalle);
});
cliente.on('auth_failure', m => { listo = false; detalle = 'Falló la autenticación: ' + m; console.error('[WhatsApp] ' + detalle); });
cliente.on('disconnected', r => {
  listo = false; detalle = 'Desconectado: ' + r + '. Reiniciando…'; console.warn('[WhatsApp] ' + detalle);
  setTimeout(async () => {
    try { await cliente.destroy(); } catch (e) { }
    cliente.initialize().catch(e => { detalle = 'No se pudo reiniciar: ' + e.message; console.error(e); });
  }, 5000);
});

/* Puente opcional con Claude Code (uso personal, WHATSAPP_PUENTE_CLAUDE=1 en .env; apagado por defecto).
   Lo que el dueño del número se escribe en su chat «Tú» se pasa al servidor local «Voz a Claude»,
   que lo pega en la ventana de Claude. Los mensajes de otras personas se ignoran. */
const PUENTE = process.env.WHATSAPP_PUENTE_CLAUDE === '1';
const misIds = new Set((process.env.WHATSAPP_MI_LID || '').split(',').map(s => s.trim()).filter(Boolean));
const MARCA_RESPUESTA = '🤖';   // las respuestas de Claude empiezan así y no se reenvían (evita bucles)
function vozPin() {
  try {
    const cfg = process.env.VOZ_CONFIG || path.join(require('node:os').homedir(), 'Herramientas', 'VozAClaude', 'config.json');
    return JSON.parse(fs.readFileSync(cfg, 'utf8')).pin;
  } catch (e) { return ''; }
}
function alPuente(ruta, cuerpo, tipo) {
  return new Promise((ok, mal) => {
    const req = require('node:https').request({
      host: '127.0.0.1', port: 8765, path: ruta, method: 'POST', rejectUnauthorized: false,
      headers: { 'X-Pin': vozPin(), 'X-Origen': 'WhatsApp', 'Content-Type': tipo, 'Content-Length': cuerpo.length },
    }, r => { let d = ''; r.on('data', c => d += c); r.on('end', () => ok(r.statusCode + ' ' + d)); });
    req.on('error', mal);
    req.end(cuerpo);
  });
}
if (PUENTE) {
  cliente.on('message_create', async msg => {
    try {
      if (!msg.fromMe) return;
      // Solo mi chat conmigo mismo. Con los identificadores nuevos de WhatsApp (@lid) «from» y «to» pueden
      // venir en formatos distintos, así que también se compara contra mi número y el id del chat.
      const yo = cliente.info?.wid?.user || '';
      const usuario = id => String(id || '').split('@')[0].split(':')[0];
      // Mis identificadores: el número (@c.us) y el id nuevo (@lid). El @lid se aprende de mis propios mensajes
      // (cuando «to» y «from» son iguales) o se fija con WHATSAPP_MI_LID en .env.
      misIds.add(yo);
      if (msg.to === msg.from) misIds.add(usuario(msg.to));
      let esMio = msg.to === msg.from || (misIds.has(usuario(msg.to)) && misIds.has(usuario(msg.from)));
      if (!esMio) {
        const chat = await msg.getChat().catch(() => null);
        esMio = !!chat && (usuario(chat.id?._serialized) === yo || usuario(chat.id?._serialized) === usuario(msg.from));
      }
      if (process.env.WHATSAPP_PUENTE_DEBUG === '1') console.log(`[Puente] fromMe to=${msg.to} from=${msg.from} tipo=${msg.type} mio=${esMio}`);
      if (!esMio) return;
      if ((msg.body || '').startsWith(MARCA_RESPUESTA)) return;     // respuesta de Claude
      if (msg.hasMedia && (msg.type === 'ptt' || msg.type === 'audio')) {
        const m = await msg.downloadMedia();
        console.log('[Puente] nota de voz -> Claude: ' + await alPuente('/subir', Buffer.from(m.data, 'base64'), m.mimetype.split(';')[0]));
      } else if (msg.body && msg.type === 'chat') {
        console.log('[Puente] mensaje -> Claude: ' + await alPuente('/texto', Buffer.from(JSON.stringify({ texto: msg.body })), 'application/json'));
      }
    } catch (e) {
      console.error('[Puente] No llegó a Claude:', e.message);
      try { await msg.reply(MARCA_RESPUESTA + ' No pude pasarlo a Claude (¿está encendido Voz a Claude?): ' + e.message); } catch (_) { }
    }
  });
  console.log('[Puente] Activado: tu chat «Tú» va directo a Claude');
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
      <title>Renueva TI · Vincular WhatsApp</title>
      <body style="font-family:Arial;background:#00102E;color:#fff;text-align:center;padding:30px">
      <h2>Renueva <span style="color:#2DCAE3">TI</span> · Vincular WhatsApp de pruebas</h2>
      ${listo ? '<p style="font-size:20px">✔ ' + detalle + '</p>'
        : qrActual ? `<p>En el celular de PRUEBAS: WhatsApp → Dispositivos vinculados → Vincular un dispositivo</p>
            <img src="${qrActual}" style="background:#fff;padding:10px;border-radius:12px">`
          : '<p>' + detalle + '</p>'}
      <p style="color:#B9C6DA">La página se actualiza sola cada 5 segundos.</p></body>`);
    return;
  }
  if (req.headers['x-token'] !== TOKEN) return responder(res, 401, { ok: false, error: 'Token inválido' });
  if (req.method === 'GET' && req.url === '/estado') return responder(res, 200, { listo, detalle });
  if (req.method === 'POST' && req.url === '/apagar') {   // cierre ordenado: guarda la sesión antes de salir
    responder(res, 200, { ok: true });
    console.log('[WhatsApp] Apagando de forma ordenada…');
    cliente.destroy().catch(() => { }).finally(() => process.exit(0));
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
cliente.initialize().catch(e => { detalle = 'No se pudo iniciar el navegador: ' + e.message; console.error(e); });
