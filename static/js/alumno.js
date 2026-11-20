/* Renueva TI · App del alumno (PWA). Pantallas A1–A5 del prototipo navegable del E3,
   ahora conectadas al servidor real y con registro sin internet. */
(function () {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const params = new URLSearchParams(location.search);
  const token = params.get('t');
  const st = { simOffline: false, paquete: null, confId: null, minuto: null, nc: '', nip: '', t0: 0 };

  if (token) {
    const p = token.split('.');
    st.confId = parseInt(p[0], 10); st.minuto = parseInt(p[1], 10);
  }

  const enLinea = () => navigator.onLine && !st.simOffline;
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const nuevoUUID = () => (crypto.randomUUID ? crypto.randomUUID() :
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16);
    }));

  async function sha16(texto) {
    if (!(crypto.subtle && crypto.subtle.digest)) return null;   // solo en HTTPS
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
  }

  function toast(t) {
    const e = $('#toast'); e.textContent = t; e.style.display = 'block';
    clearTimeout(toast.h); toast.h = setTimeout(() => e.style.display = 'none', 4000);
  }

  function mostrar(id) {
    $$('#phone [data-screen]').forEach(e => e.classList.toggle('on', e.dataset.screen === id));
    if (id === 'A1') renderA1();
    if (id === 'A5') renderA5();
    window.scrollTo(0, 0);
  }

  function pintarRed() {
    const n = $('#net');
    n.className = 'pill ' + (enLinea() ? 'on' : 'off');
    n.textContent = enLinea() ? '● En línea' : (st.simOffline ? '● Sin internet (simulado)' : '● Sin internet');
  }

  // ------------------------------------------------------------ datos
  async function descargarPaquetes() {
    if (!enLinea()) return;
    try {
      const r = await fetch('/api/conferencias/activas', { cache: 'no-store' });
      const j = await r.json();
      const ids = j.conferencias.map(c => c.id);
      if (st.confId && !ids.includes(st.confId)) ids.push(st.confId);
      for (const id of ids) {
        const rp = await fetch('/api/paquete/' + id, { cache: 'no-store' });
        if (rp.ok) await rtDB.put('paquetes', await rp.json());
      }
    } catch (e) { /* sin red: se usan los paquetes guardados */ }
  }

  async function sincronizar(avisar) {
    if (!enLinea()) return [];
    const enviados = await rtSync();
    if (avisar && enviados.length) toast('Conexión recuperada: ' + (enviados.length === 1 ? 'tu registro se envió' : enviados.length + ' registros se enviaron') + ' automáticamente.');
    return enviados;
  }

  async function guardarPendiente(datos, conferencia) {
    await rtDB.put('pendientes', { uuid: datos.uuid, conferencia, datos });
    if (st.simOffline) return;   // en la simulación el navegador sí tiene red: no adelantar el envío
    try {   // Background Sync donde exista (Chrome/Android); en iPhone se envía al abrir la app (riesgo R1)
      const reg = await navigator.serviceWorker?.ready;
      if (reg && reg.sync) await reg.sync.register('rt-sync');
    } catch (e) { }
  }

  // ------------------------------------------------------------ A1
  async function renderA1() {
    pintarRed();
    const paquetes = await rtDB.all('paquetes').catch(() => []);
    const pend = await rtDB.all('pendientes').catch(() => []);
    let html = '', puede = false;
    if (token) {
      st.paquete = paquetes.find(p => p.id === st.confId) || null;
      if (st.paquete) {
        const p = st.paquete;
        html = `<div class="card hl"><span class="badge b-info">Conferencia</span>
          <h2 style="margin-top:8px">${esc(p.nombre)}</h2>
          <p class="mut">${esc(p.lugar)} · ${esc(p.fecha)} · ${esc(p.horario)}<br>Congreso Académico</p></div>`;
        if (st.minuto < p.inicio || st.minuto > p.cierre) {
          html += `<div class="msg err"><b>Registro cerrado.</b> Este QR es de un horario fuera de la conferencia. Escanea el QR que se muestra ahora en la sala.</div>`;
        } else puede = true;
      } else {
        html = `<div class="msg err"><b>No tenemos los datos de esta conferencia en tu celular.</b> ${enLinea()
          ? 'No pudimos descargarlos; recarga la página.'
          : 'Conéctate a internet un momento o pide al profesor que te registre con apoyo.'}</div>`;
      }
    } else {
      html = `<div class="card hl"><span class="badge b-info">Cómo registrarte</span>
        <h2 style="margin-top:8px">Escanea el QR de la conferencia</h2>
        <p class="mut">El profesor lo muestra en la sala. Abre la cámara de tu celular y apunta al código.</p></div>`;
    }
    $('#a1conf').innerHTML = html;
    $('#a1start').style.display = puede ? '' : 'none';
    const lista = paquetes.length ? paquetes.map(p => esc(p.nombre)).join(', ') : 'ninguna todavía';
    $('#a1status').textContent = (enLinea()
      ? '✔ Estás en línea. '
      : '✔ Sin internet, pero puedes registrarte con los datos guardados. ') + 'Conferencias guardadas en tu celular: ' + lista + '.';
    $('#a1pend').innerHTML = pend.length
      ? `<div class="msg local"><span class="badge b-wait">${pend.length} pendiente${pend.length > 1 ? 's' : ''} de envío</span><p class="mut" style="margin-top:6px">Se enviará${pend.length > 1 ? 'n' : ''} solo${pend.length > 1 ? 's' : ''} cuando haya conexión.</p></div>` : '';
  }

  // ------------------------------------------------------------ A2
  function errA2(t) { const e = $('#nc-err'); e.textContent = t; e.style.display = t ? 'block' : 'none'; }

  async function yaRegistradoLocal(nc) {
    const pend = await rtDB.all('pendientes');
    const p = pend.find(x => x.datos.no_control === nc && x.datos.conferencia_id === st.confId);
    if (p) return { tipo: 'pendiente' };
    const regs = await rtDB.all('registros');
    const r = regs.find(x => x.no_control === nc && x.conferencia_id === st.confId && x.folio !== '—');
    return r ? { tipo: 'registro', registro: r } : null;
  }

  $('#a2next').onclick = async () => {
    const nc = $('#nc').value.trim();
    if (!/^\d{8}$/.test(nc)) return errA2('El número de control debe tener 8 dígitos. Revísalo y vuelve a intentarlo.');
    const nip = $('#nip').value.trim();
    if (!/^\d{4}$/.test(nip)) return errA2('Escribe tu NIP de 4 dígitos: es el mismo con el que entras al SIIC.');
    errA2(''); st.nc = nc; st.nip = nip;
    const local = await yaRegistradoLocal(nc);
    if (local) {
      if (local.tipo === 'pendiente') return mostrar('A4b');
      return mostrarResultado(local.registro, true);
    }
    if (enLinea()) {
      try {
        const r = await fetch('/api/identificar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ no_control: nc, nip, conferencia: st.confId }) });
        const j = await r.json();
        if (!j.ok) return errA2(j.error);
        if (j.ya_registrado) return mostrarResultado(j.registro, true);
        return confirmar(j.nombre_parcial);
      } catch (e) { /* se cayó la red justo ahora: seguimos sin internet */ }
    }
    const h = await sha16(nc);
    if (h === null) return confirmar(null);
    const parcial = st.paquete && st.paquete.padron[h];
    if (!parcial) return errA2('No encontramos ese número en los datos guardados de esta conferencia. Revisa que esté bien escrito; si es correcto, acude con el profesor.');
    confirmar(parcial);
  };

  function confirmar(parcial) {
    if (!parcial) { return iniciarCuestionario(); }
    $('#a2hola').textContent = 'Hola, ' + parcial;
    $('#a2form').style.display = 'none'; $('#a2next').style.display = 'none';
    $('#a2confirm').style.display = '';
  }
  function resetA2() {
    $('#a2form').style.display = ''; $('#a2next').style.display = ''; $('#a2confirm').style.display = 'none';
  }
  $('#a2si').onclick = () => iniciarCuestionario();
  $('#a2no').onclick = () => { resetA2(); $('#nip').value = ''; $('#nc').focus(); $('#nc').select(); };

  // ------------------------------------------------------------ A3
  function iniciarCuestionario() {
    resetA2();
    const p = st.paquete;
    $('#qs').innerHTML = p.preguntas.map((q, i) =>
      `<fieldset style="border:0;padding:0;margin:0 0 10px"><legend style="font-weight:600;margin-bottom:6px">${i + 1}. ${esc(q.texto)}</legend>` +
      q.opciones.map((o, j) => `<label class="opt"><input type="radio" name="q${i}" value="${j}"> ${esc(o)}</label>`).join('') +
      `</fieldset>`).join('');
    $('#a3err').style.display = 'none';
    st.t0 = Date.now();
    iniciarEspera(p.tiempo_minimo_seg || 0);
    mostrar('A3');
  }

  // D-13: el botón muestra cuánto falta para el tiempo mínimo (RN-15) y solo se habilita al cumplirlo.
  // Antes el alumno enviaba antes de tiempo y el registro llegaba «No válido» sin aviso.
  function faltaEspera() {
    return Math.max(0, Math.ceil((st.minSeg || 0) - (Date.now() - st.t0) / 1000));
  }
  function iniciarEspera(minSeg) {
    clearInterval(st.relojEspera);
    st.minSeg = minSeg;
    const b = $('#a3send'), aviso = $('#a3espera');
    const pintar = () => {
      const f = faltaEspera();
      b.disabled = f > 0;
      b.textContent = f > 0 ? `Podrás enviar en ${Math.floor(f / 60)}:${String(f % 60).padStart(2, '0')}` : 'Enviar mi registro';
      aviso.style.display = f > 0 ? 'block' : 'none';
      if (!f) clearInterval(st.relojEspera);
    };
    aviso.textContent = `Para que tu registro sea válido, tómate al menos ${Math.round(minSeg / 60 * 10) / 10} min para leer y responder (${Math.round(minSeg / Math.max(1, st.paquete.preguntas.length))} s por pregunta).`;
    pintar();
    if (minSeg > 0) st.relojEspera = setInterval(pintar, 500);
  }

  $('#a3send').onclick = async () => {
    const p = st.paquete;
    const respuestas = p.preguntas.map((_, i) => {
      const m = document.querySelector(`input[name="q${i}"]:checked`); return m ? parseInt(m.value, 10) : null;
    });
    const faltan = respuestas.filter(r => r === null).length;
    if (faltan) {
      const e = $('#a3err'); e.style.display = 'block';
      e.textContent = `Te falta${faltan > 1 ? 'n' : ''} ${faltan} pregunta${faltan > 1 ? 's' : ''} por responder. Contéstala${faltan > 1 ? 's' : ''} para poder enviar.`;
      return;
    }
    if (faltaEspera() > 0) return;   // D-13: aún no se cumple el tiempo mínimo
    clearInterval(st.relojEspera);
    $('#a3send').disabled = true;
    const datos = {
      uuid: nuevoUUID(), token, no_control: st.nc, nip: st.nip, respuestas, conferencia_id: st.confId,
      tiempo_seg: Math.round((Date.now() - st.t0) / 1000), capturado_en: new Date().toISOString(), origen: 'celular'
    };
    await guardarPendiente(datos, p.nombre);      // primero se guarda: nunca se pierde (NFR-08, NFR-11)
    if (enLinea()) {
      await sincronizar(false);
      const r = await rtDB.get('registros', datos.uuid);
      if (r) return mostrarResultado(r, false);
    }
    const pend = await rtDB.all('pendientes');
    $('#a4bpend').textContent = pend.length + ' pendiente' + (pend.length > 1 ? 's' : '') + ' de envío';
    mostrar('A4b');
  };

  // ------------------------------------------------------------ A4a
  function mostrarResultado(r, previo) {
    let h;
    if (r.folio === '—') {
      h = `<div class="msg err"><h2>No pudimos registrarte</h2><p style="margin-top:6px">${esc(r.motivo)}</p></div>`;
    } else if (previo || r.duplicado) {
      h = `<div class="msg info"><h2>Ya tenías un registro en esta conferencia</h2><p style="margin-top:6px">Tu folio es</p><p class="big">${esc(r.folio)}</p><p class="mut">Solo se permite un registro por conferencia. Estado: ${esc(r.estado)}.</p></div>`;
    } else if (r.valido) {
      h = `<div class="msg ok"><h2>¡Registro recibido!</h2><p style="margin-top:6px">Tu folio es</p><p class="big">${esc(r.folio)}</p><p class="mut">${esc(r.recibido)} h · Te avisaremos por correo y WhatsApp cuando tu registro se cargue en el SIIC.</p></div>`;
    } else {
      h = `<div class="msg err"><h2>Tu registro no fue válido</h2><p style="margin-top:6px">Folio <b>${esc(r.folio)}</b></p><p style="margin-top:6px">Motivo: ${esc(r.motivo)}.</p><p class="mut" style="margin-top:6px">El cuestionario no se repite. Si crees que es un error, comunícate con: ${esc(r.contacto)}.</p></div>`;
    }
    $('#a4amsg').innerHTML = h;
    mostrar('A4a');
  }

  // ------------------------------------------------------------ A5
  function tarjeta(r) {
    const cls = r.estado === 'Cargado en el SIIC' ? 'b-ok' : (r.valido ? 'b-info' : 'b-bad');
    const pct = r.valido ? ((r.paso || 1) + 1) * 25 : 25;
    return `<div class="card"><span class="badge ${cls}">${esc(r.estado)}</span>
      <h3 style="margin-top:8px">${esc(r.conferencia)}</h3>
      <p class="mut">Folio ${esc(r.folio)}${r.motivo ? ' · ' + esc(r.motivo) : ''}</p>
      ${r.valido ? `<div class="prog" style="margin-top:6px"><i style="width:${pct}%"></i></div>` : ''}</div>`;
  }

  async function renderA5() {
    const pend = await rtDB.all('pendientes');
    const regs = await rtDB.all('registros');
    let h = pend.map(p => `<div class="card"><span class="badge b-wait">Pendiente de envío</span><h3 style="margin-top:8px">${esc(p.conferencia)}</h3><p class="mut">Guardado en tu celular. Se enviará cuando haya conexión.</p></div>`).join('');
    h += regs.map(tarjeta).join('');
    $('#a5list').innerHTML = h || '<p class="mut">Todavía no hay registros en este celular. Si te registraste en otro, consulta tu estado actualizado abajo.</p>';
    $('#a5consulta').style.display = enLinea() ? '' : 'none';
  }

  function errA5(t) { const e = $('#a5err'); e.textContent = t; e.style.display = t ? 'block' : 'none'; }
  $('#a5pedir').onclick = async () => {
    const nc = $('#a5nc').value.trim();
    if (!/^\d{8}$/.test(nc)) return errA5('El número de control debe tener 8 dígitos.');
    errA5('');
    try {
      const r = await fetch('/api/estado/codigo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ no_control: nc }) });
      const j = await r.json();
      if (!j.ok) return errA5(j.error);
      $('#a5correo').textContent = 'Enviamos el código a ' + j.correo + '. Revisa también la carpeta de spam.';
      $('#a5paso1').style.display = 'none'; $('#a5paso2').style.display = '';
    } catch (e) { errA5('No hay conexión. Inténtalo cuando tengas señal.'); }
  };
  $('#a5ver').onclick = async () => {
    try {
      const r = await fetch('/api/estado', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ no_control: $('#a5nc').value.trim(), codigo: $('#a5cod').value.trim() }) });
      const j = await r.json();
      if (!j.ok) return errA5(j.error);
      errA5('');
      for (const reg of j.registros) await rtDB.put('registros', Object.assign({ no_control: $('#a5nc').value.trim() }, reg));
      $('#a5paso2').style.display = 'none'; $('#a5paso1').style.display = '';
      $('#a5list').innerHTML = `<p class="mut">Hola, ${esc(j.nombre_parcial)}. Estado actualizado:</p>` +
        (j.registros.map(tarjeta).join('') || '<p class="mut">No tienes registros todavía. Escanea el QR en la próxima conferencia.</p>');
    } catch (e) { errA5('No hay conexión. Inténtalo cuando tengas señal.'); }
  };

  // ------------------------------------------------------------ eventos
  $$('[data-go]').forEach(b => b.onclick = () => mostrar(b.dataset.go));
  $('#a1start').onclick = () => { $('#nc').value = ''; $('#nip').value = ''; st.nip = ''; resetA2(); errA2(''); mostrar('A2'); setTimeout(() => $('#nc').focus(), 50); };
  $('#net').onclick = async () => {
    st.simOffline = !st.simOffline; pintarRed();
    if (enLinea()) { await sincronizar(true); }
    const cur = ($$('#phone [data-screen].on')[0] || {}).dataset?.screen;
    if (cur === 'A1' || cur === 'A5') mostrar(cur);
    if (cur === 'A4b' && enLinea()) {
      const regs = await rtDB.all('registros'); const ult = regs[regs.length - 1];
      if (ult && !(await rtDB.all('pendientes')).length) mostrarResultado(ult, false);
    }
  };
  window.addEventListener('online', async () => { pintarRed(); await sincronizar(true); renderA1(); });
  window.addEventListener('offline', () => { pintarRed(); renderA1(); });
  setInterval(() => sincronizar(true), 20000);

  async function iniciar() {
    pintarRed();
    if ('serviceWorker' in navigator && window.isSecureContext) {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { });
    }
    mostrar('A1');
    await descargarPaquetes();
    await sincronizar(true);
    mostrar('A1');
  }
  iniciar();
})();
