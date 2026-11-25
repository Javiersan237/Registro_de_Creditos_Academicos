"""Pantallas por rol (E3 §5.2): Profesor P1, Comité C1-C3, Servicios Escolares S1."""
import io
import json
from functools import wraps

import qrcode
import qrcode.image.svg
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import firma, notificaciones, servicios
from .context import GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS, roles_de
from .forms import ConferenciaForm, PadronForm
from .models import CARRERAS, CARRERAS_DICT, Aviso, Bitacora, Configuracion, Conferencia, Lote, Pregunta, Registro
from .servicios import ErrorRegistro


def rol_requerido(*grupos):
    """NFR-07: cada rol ve solo lo que le corresponde."""
    def deco(vista):
        @wraps(vista)
        @login_required
        def envuelta(request, *args, **kwargs):
            if not roles_de(request.user) & set(grupos):
                return render(request, "registro/sin_permiso.html", status=403)
            return vista(request, *args, **kwargs)
        return envuelta
    return deco


# ---------------------------------------------------------------- generales
def portada(request):
    return render(request, "registro/portada.html")


def acerca(request):
    """Acerca de: la institución al frente y Renueva TI como empresa consultora."""
    return render(request, "registro/acerca.html")


def app_alumno(request):
    """Interfaz del alumno (PWA). La misma página sirve en línea y sin internet."""
    return render(request, "registro/alumno.html")


def service_worker(request):
    with open(settings.BASE_DIR / "static" / "js" / "sw.js", encoding="utf-8") as f:
        resp = HttpResponse(f.read(), content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


def manifest(request):
    data = {
        "name": "Registro de asistencia · TecNM Matehuala", "short_name": "Asistencia ITMH",
        "start_url": "/app/", "scope": "/", "display": "standalone",
        "background_color": "#1B396A", "theme_color": "#1B396A", "lang": "es-MX",
        "icons": [{"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png",
                   "purpose": "any maskable"}],
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")


@login_required
def inicio(request):
    r = roles_de(request.user)
    if GRUPO_COMITE in r:
        return redirect("comite")
    if GRUPO_SERVICIOS in r:
        return redirect("servicios")
    if GRUPO_PROFESOR in r:
        return redirect("profesor")
    return render(request, "registro/sin_permiso.html", status=403)


# ---------------------------------------------------------------- Profesor (P1)
@rol_requerido(GRUPO_PROFESOR)
def profesor(request):
    qs = Conferencia.objects.all() if request.user.is_superuser else \
        Conferencia.objects.filter(profesor=request.user)
    return render(request, "registro/profesor_lista.html", {"conferencias": qs})


def _svg_qr(texto):
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def _base_url(request):
    # Versión del salón: el lanzador fija la dirección de la laptop en la red (URL_PUBLICA), para que el QR
    # funcione en los celulares aunque el profesor abra el panel como «localhost».
    return settings.URL_PUBLICA.rstrip("/") or request.build_absolute_uri("/").rstrip("/")


@rol_requerido(GRUPO_PROFESOR)
def profesor_panel(request, pk):
    c = get_object_or_404(Conferencia, pk=pk)
    if not request.user.is_superuser and c.profesor_id != request.user.pk:
        return HttpResponseForbidden("Esta conferencia está asignada a otro profesor.")
    base = _base_url(request)
    # FR-02: el paquete completo, un QR firmado por cada minuto de la ventana.
    # Va dentro de la página para que siga funcionando si la laptop pierde internet.
    qrs = [{"m": m, "url": f"{base}/app/?t={tok}", "svg": _svg_qr(f"{base}/app/?t={tok}")}
           for m, tok in firma.paquete_qr(c)]
    return render(request, "registro/profesor_panel.html", {
        "c": c, "qrs_json": json.dumps(qrs), "total_qr": len(qrs),
        "inicio": firma.minuto_de(c.inicio_dt()), "cierre": firma.minuto_de(c.cierre_dt()),
    })


@rol_requerido(GRUPO_PROFESOR)
def profesor_estado(request, pk):
    c = get_object_or_404(Conferencia, pk=pk)
    qs = c.registros.all()
    return JsonResponse({
        "recibidos": qs.count(),
        "pendientes_sync": qs.filter(sincronizado_central=False).count() if settings.MODO_LOCAL else 0,
        "ultimos": [{"folio": r.folio, "alumno": r.alumno.nombre_parcial(), "valido": r.valido,
                     "hora": timezone.localtime(r.recibido).strftime("%H:%M")}
                    for r in qs.select_related("alumno")[:6]],
    })


@require_POST
@rol_requerido(GRUPO_PROFESOR)
def profesor_asistido(request, pk):
    c = get_object_or_404(Conferencia, pk=pk)
    try:
        r = servicios.registrar_asistido(conferencia=c, no_control=request.POST.get("no_control"),
                                         motivo=request.POST.get("motivo"), usuario=request.user)
        if r.valido:
            messages.success(request, f"Registro asistido guardado: folio {r.folio} ({r.alumno.nombre_parcial()}).")
        else:
            messages.warning(request, f"Se guardó el folio {r.folio}, pero no es válido: {r.motivo}.")
    except ErrorRegistro as e:
        messages.error(request, str(e))
    return redirect("profesor_panel", pk=pk)


@require_POST
@rol_requerido(GRUPO_PROFESOR)
def profesor_sincronizar(request, pk):
    """FR-24 (modo B): sube al servidor central los registros guardados en la laptop."""
    c = get_object_or_404(Conferencia, pk=pk)
    if not settings.MODO_LOCAL or not settings.CENTRAL_URL:
        messages.info(request, "Estás conectado al servidor central: los registros ya llegan directo. "
                               "No hay nada que sincronizar.")
        return redirect("profesor_panel", pk=pk)
    ok = fallos = 0
    for r in c.registros.filter(sincronizado_central=False, origen__in=[Registro.CELULAR, Registro.RED_LOCAL]):
        try:
            resp = requests.post(f"{settings.CENTRAL_URL.rstrip('/')}/api/registros", timeout=15, json={
                "uuid": str(r.uuid), "token": r.token, "no_control": r.alumno_id, "respuestas": r.respuestas,
                "tiempo_seg": r.tiempo_seg, "origen": Registro.RED_LOCAL,
                "sync_firma": firma.firma_sync(r.uuid),  # la laptop ya verificó el NIP del alumno
                "telefono": r.alumno.telefono if r.alumno.telefono_del_alumno else "",
                "capturado_en": r.capturado_en.isoformat() if r.capturado_en else None})
            if resp.status_code in (200, 201):
                r.sincronizado_central = True
                r.save(update_fields=["sincronizado_central"])
                ok += 1
            else:
                fallos += 1
        except requests.RequestException:
            fallos += 1
    Bitacora.registrar(request.user, "Sincronización modo local", c, f"{ok} enviados, {fallos} con error")
    if fallos:
        messages.warning(request, f"Se enviaron {ok} registros; {fallos} no se pudieron enviar. "
                                  "Revisa la conexión e inténtalo de nuevo: no se duplican.")
    else:
        messages.success(request, f"Sincronizado: {ok} registros enviados al servidor central.")
    return redirect("profesor_panel", pk=pk)


# ---------------------------------------------------------------- Comité (C1, C2, C3)
@rol_requerido(GRUPO_COMITE)
def comite(request):
    """C1: conferencias y alta de una nueva (FR-01)."""
    form = ConferenciaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = form.save(commit=False)
        c.carreras = ",".join(form.cleaned_data["carreras_sel"])
        c.creada_por = request.user
        c.save()
        for i, (texto, opciones, correcta) in enumerate(form.cleaned_data["preguntas"], 1):
            Pregunta.objects.create(conferencia=c, orden=i, texto=texto, opciones=opciones, correcta=correcta)
        Bitacora.registrar(request.user, "Alta de conferencia", c,
                           f"{len(form.cleaned_data['preguntas'])} preguntas, {firma.paquete_qr(c).__len__()} QR")
        messages.success(request, f"Conferencia guardada. Se generaron {len(firma.paquete_qr(c))} QR firmados "
                                  "(uno por minuto) y el paquete ya está disponible para los celulares.")
        return redirect("comite")
    conferencias = Conferencia.objects.annotate(n_reg=Count("registros"), n_preg=Count("preguntas", distinct=True))
    return render(request, "registro/comite_conferencias.html", {"form": form, "conferencias": conferencias})


def _filtro_conf(request):
    cid = request.GET.get("conf") or request.POST.get("conf")
    return Conferencia.objects.filter(pk=cid).first() if cid else None


def consulta(request, accion, objeto):
    """Versión del salón: también queda en la bitácora quién CONSULTÓ datos personales (no solo quién los cambió).
    Una entrada por usuario, pantalla y objeto cada 10 minutos, para no llenar la bitácora al recargar."""
    from django.core.cache import cache
    clave = f"consulta:{request.user.pk}:{accion}:{objeto}"
    if cache.add(clave, 1, 600):
        Bitacora.registrar(request.user, f"Consulta: {accion}", objeto, request.META.get("REMOTE_ADDR", ""))


@rol_requerido(GRUPO_COMITE)
def tablero(request):
    """C2: estado por carrera (FR-08). La suma de los estados coincide con el total."""
    consulta(request, "tablero por carrera", "Registros")
    conf = _filtro_conf(request)
    qs = Registro.objects.all()
    if conf:
        qs = qs.filter(conferencia=conf)
    filas = []
    for clave, nombre in CARRERAS:
        q = qs.filter(alumno__carrera=clave)
        d = q.aggregate(total=Count("id"), validos_pend=Count("id", filter=Q(valido=True, lote__isnull=True)),
                        enviados=Count("id", filter=Q(valido=True, lote__isnull=False)),
                        no_validos=Count("id", filter=Q(valido=False)))
        filas.append({"clave": clave, "nombre": nombre, **d})
    tot = qs.aggregate(total=Count("id"), validos=Count("id", filter=Q(valido=True)),
                       no_validos=Count("id", filter=Q(valido=False)),
                       pendientes=Count("id", filter=Q(valido=True, lote__isnull=True)))
    return render(request, "registro/comite_tablero.html", {
        "filas": filas, "tot": tot, "conf": conf, "conferencias": Conferencia.objects.all()})


@rol_requerido(GRUPO_COMITE)
def detalle_carrera(request, carrera):
    """C3: alumno por alumno, con puntaje, tiempo y motivo (FR-09)."""
    consulta(request, "detalle por carrera", carrera)
    conf = _filtro_conf(request)
    qs = Registro.objects.filter(alumno__carrera=carrera).select_related("alumno", "conferencia", "lote")
    if conf:
        qs = qs.filter(conferencia=conf)
    return render(request, "registro/comite_detalle.html", {
        "registros": qs.order_by("valido", "alumno_id"), "carrera": CARRERAS_DICT.get(carrera, carrera),
        "conf": conf})


@require_POST
@rol_requerido(GRUPO_COMITE)
def enviar(request):
    """FR-10: botón «Enviar»."""
    conf = _filtro_conf(request)
    lote = servicios.enviar_validos(request.user, conf)
    if lote:
        messages.success(request, f"Enviado a Servicios Escolares: lote {lote.codigo} con "
                                  f"{lote.registros.count()} registros válidos. Quedó en la bitácora.")
    else:
        messages.info(request, "No hay registros válidos nuevos para enviar. Nada se duplicó.")
    return redirect(f"{request.META.get('HTTP_REFERER') or '/comite/tablero/'}")


# ---------------------------------------------------------------- Servicios Escolares (S1)
@rol_requerido(GRUPO_SERVICIOS)
def servicios_inicio(request):
    form = PadronForm(request.POST or None, request.FILES or None)
    resultado = None
    if request.method == "POST" and form.is_valid():
        try:
            texto = form.cleaned_data["archivo"].read().decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = None
            messages.error(request, "El archivo no está en UTF-8. Guárdalo como «CSV UTF-8» y vuelve a cargarlo.")
        if texto is not None:
            try:
                resultado = servicios.cargar_padron(texto, request.user)
                messages.success(request, f"Padrón cargado: {resultado['aceptadas']} filas aceptadas, "
                                          f"{len(resultado['rechazadas'])} rechazadas.")
            except ErrorRegistro as e:
                messages.error(request, str(e))
    lotes = Lote.objects.annotate(n=Count("registros"))
    from .models import Alumno
    return render(request, "registro/servicios_inicio.html", {
        "lotes": lotes, "form": form, "resultado": resultado, "n_alumnos": Alumno.objects.count(),
        "columnas": ",".join(servicios.COLUMNAS_PADRON)})


@rol_requerido(GRUPO_SERVICIOS)
def lote_detalle(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    consulta(request, "lote", lote)
    filas = servicios.filas_csv(lote)
    return render(request, "registro/servicios_lote.html", {
        "lote": lote, "filas": filas[:8], "n": len(filas), "columnas": servicios.COLUMNAS_CSV,
        "problemas": servicios.problemas_csv(filas), "contacto": Configuracion.actual().contacto_encargado,
        "avisos": Aviso.objects.filter(alumno__registros__lote=lote).distinct()[:30]})


@rol_requerido(GRUPO_SERVICIOS)
def lote_csv(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    contenido, problemas = servicios.generar_csv(lote, request.user)
    if problemas:
        messages.error(request, "No se descargó el archivo: hay filas con columnas obligatorias vacías: " +
                       "; ".join(f"fila {f}: {', '.join(c)}" for f, c in problemas[:10]))
        return redirect("lote_detalle", pk=pk)
    cod = settings.EXPORT_CODIFICACION
    resp = HttpResponse(contenido.encode(cod, errors="replace"), content_type=f"text/csv; charset={cod}")
    resp["Content-Disposition"] = f'attachment; filename="siic_lote_{lote.codigo}.csv"'
    return resp


@require_POST
@rol_requerido(GRUPO_SERVICIOS)
def lote_confirmar(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    try:
        n = servicios.confirmar_carga(lote, request.user)
        messages.success(request, f"Carga confirmada. Se están enviando avisos por correo y WhatsApp a {n} alumnos.")
    except ErrorRegistro as e:
        messages.error(request, str(e))
    return redirect("lote_detalle", pk=pk)


@require_POST
@rol_requerido(GRUPO_SERVICIOS)
def lote_falla(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    try:
        n = servicios.reportar_falla(lote, request.user, request.POST.get("motivo"))
        messages.warning(request, f"Falla registrada. Se avisó a {n} alumnos con el motivo y el contacto del encargado.")
    except ErrorRegistro as e:
        messages.error(request, str(e))
    return redirect("lote_detalle", pk=pk)


@rol_requerido(GRUPO_SERVICIOS, GRUPO_COMITE)
def avisos(request):
    consulta(request, "avisos a alumnos", "Teléfonos y mensajes")
    if request.method == "POST":
        n = notificaciones.reintentar_errores()
        messages.info(request, f"Se reintentaron {n} avisos con error o pendientes.")
        return redirect("avisos")
    return render(request, "registro/avisos.html", {
        "avisos": Aviso.objects.select_related("alumno")[:150], "wa": notificaciones.estado_whatsapp(),
        "correo_real": "smtp" in settings.EMAIL_BACKEND,
        "resumen": Aviso.objects.values("canal", "estado").annotate(n=Count("id")).order_by("canal", "estado")})


@rol_requerido(GRUPO_SERVICIOS, GRUPO_COMITE)
def bitacora(request):
    from .integridad import verificar
    revision = None
    if request.method == "POST":
        revision = verificar()
        Bitacora.registrar(request.user, "Verificación de integridad", "Base de datos",
                           "Sin alteraciones" if revision["ok"] else f"{len(revision['problemas'])} problema(s)")
    return render(request, "registro/bitacora.html", {"entradas": Bitacora.objects.select_related("usuario")[:200],
                                                      "revision": revision})
