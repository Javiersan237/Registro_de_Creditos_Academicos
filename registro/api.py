"""API REST del E3 §3.5 (vistas JSON de Django).

Las rutas del alumno no usan sesión: se protegen con el QR firmado y, para
consultar el estado, con un código de 6 dígitos enviado al correo (FR-16).
"""
import hashlib
import json
import uuid as uuidlib
from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import firma, notificaciones, validacion
from .models import Alumno, CodigoConsulta, Configuracion, Conferencia, Registro
from .servicios import ErrorRegistro, buscar_alumno, registrar_por_qr, verificar_nip


def _json(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        raise ErrorRegistro("La solicitud no tiene un formato válido.")


def _error(e):
    return JsonResponse({"ok": False, "error": str(e)}, status=getattr(e, "codigo", 400))


def _registro_json(r):
    cfg = Configuracion.actual()
    return {
        "uuid": str(r.uuid), "folio": r.folio, "conferencia": r.conferencia.nombre,
        "fecha": f"{r.conferencia.fecha:%d/%m/%Y}", "valido": r.valido, "motivo": r.motivo,
        "estado": r.estado_alumno(), "paso": r.paso(),
        "recibido": timezone.localtime(r.recibido).strftime("%d/%m/%Y %H:%M"),
        "contacto": cfg.contacto_encargado if not r.valido else "",
    }


@require_GET
def conferencias_activas(request):
    """Conferencias de hoy y de los próximos 7 días que el celular debe guardar."""
    hoy = timezone.localdate()
    qs = Conferencia.objects.filter(fecha__gte=hoy, fecha__lte=hoy + timedelta(days=7))
    return JsonResponse({"conferencias": [{"id": c.pk, "nombre": c.nombre} for c in qs]})


@require_GET
def paquete(request, pk):
    """Paquete de la conferencia para usar sin internet (FR-22).
    No incluye respuestas correctas ni la clave de firma. El padrón va como
    hash del número de control → iniciales, solo para confirmar identidad (FR-28)."""
    c = get_object_or_404(Conferencia, pk=pk)
    cfg = Configuracion.actual()
    padron = {hashlib.sha256(a.no_control.encode()).hexdigest()[:16]: a.nombre_parcial()
              for a in Alumno.objects.filter(carrera__in=c.carreras_lista)}
    return JsonResponse({
        "id": c.pk, "nombre": c.nombre, "lugar": c.lugar, "fecha": f"{c.fecha:%d/%m/%Y}",
        "horario": f"{c.hora_inicio:%H:%M} a {c.hora_fin:%H:%M} h",
        "inicio": int(c.inicio_dt().timestamp() // 60), "cierre": int(c.cierre_dt(cfg).timestamp() // 60),
        "preguntas": [{"texto": p.texto, "opciones": p.opciones} for p in c.preguntas.all()],
        "padron": padron, "descargado": timezone.now().isoformat(),
    })


@csrf_exempt
@require_POST
def identificar(request):
    """Paso 1 del registro con internet: valida el número de control y el NIP (FR-04, FR-28).
    Sin el NIP correcto no se devuelve ningún dato del alumno."""
    try:
        datos = _json(request)
        alumno = buscar_alumno(datos.get("no_control"))
        verificar_nip(alumno, datos.get("nip"))
        respuesta = {"ok": True, "nombre_parcial": alumno.nombre_parcial(), "ya_registrado": False}
        cid = datos.get("conferencia")
        if cid:
            previo = Registro.objects.filter(alumno=alumno, conferencia_id=cid).first()
            if previo:
                respuesta.update(ya_registrado=True, registro=_registro_json(previo))
        return JsonResponse(respuesta)
    except ErrorRegistro as e:
        return _error(e)


@csrf_exempt
@require_POST
def registros(request):
    """Recibe un registro. Idempotente por uuid: reenviar no duplica (FR-23)."""
    try:
        d = _json(request)
        try:
            u = uuidlib.UUID(str(d.get("uuid")))
        except ValueError:
            raise ErrorRegistro("Falta el identificador del registro. Vuelve a enviarlo desde la app.")
        capturado = parse_datetime(d["capturado_en"]) if d.get("capturado_en") else None
        origen = d.get("origen") if d.get("origen") in (Registro.CELULAR, Registro.RED_LOCAL) else Registro.CELULAR
        registro, nuevo, duplicado = registrar_por_qr(
            uuid=u, token=d.get("token", ""), no_control=d.get("no_control"), respuestas=d.get("respuestas"),
            tiempo_seg=d.get("tiempo_seg", 0), capturado_en=capturado, origen=origen, nip=d.get("nip"),
            nip_verificado=firma.firma_sync_valida(u, d.get("sync_firma")))
        return JsonResponse({"ok": True, "nuevo": nuevo, "duplicado": duplicado,
                             "registro": _registro_json(registro)}, status=201 if nuevo else 200)
    except ErrorRegistro as e:
        return _error(e)


@csrf_exempt
@require_POST
def pedir_codigo(request):
    """FR-16, paso 1: envía un código de 6 dígitos al correo institucional."""
    try:
        alumno = buscar_alumno(_json(request).get("no_control"))
        reciente = CodigoConsulta.objects.filter(alumno=alumno, usado=False,
                                                 expira__gt=timezone.now() + timedelta(minutes=9)).exists()
        if reciente:
            raise ErrorRegistro("Ya te enviamos un código hace menos de un minuto. Revisa tu correo "
                                "(también la carpeta de spam) o espera un momento.", 429)
        codigo = CodigoConsulta.nuevo(alumno)
        asunto, texto = notificaciones.msg_codigo(alumno, codigo.codigo)
        notificaciones.notificar(alumno, "codigo", asunto, texto, canales=("correo",))
        return JsonResponse({"ok": True, "correo": alumno.correo_enmascarado()})
    except ErrorRegistro as e:
        return _error(e)


@csrf_exempt
@require_POST
def estado(request):
    """FR-16, paso 2: con el código correcto devuelve los registros del alumno.
    No muestra cuántas conferencias necesita (RN-13)."""
    try:
        d = _json(request)
        alumno = buscar_alumno(d.get("no_control"))
        codigo = CodigoConsulta.objects.filter(alumno=alumno, usado=False).order_by("-expira").first()
        if not codigo or codigo.expira < timezone.now():
            raise ErrorRegistro("El código venció o no existe. Pide uno nuevo.", 403)
        if codigo.intentos >= 5:
            raise ErrorRegistro("Demasiados intentos. Pide un código nuevo.", 403)
        if str(d.get("codigo", "")).strip() != codigo.codigo:
            codigo.intentos += 1
            codigo.save(update_fields=["intentos"])
            raise ErrorRegistro("El código no coincide. Revisa el correo más reciente e inténtalo de nuevo.", 403)
        codigo.usado = True
        codigo.save(update_fields=["usado"])
        regs = alumno.registros.select_related("conferencia", "lote")
        return JsonResponse({"ok": True, "nombre_parcial": alumno.nombre_parcial(),
                             "registros": [_registro_json(r) for r in regs]})
    except ErrorRegistro as e:
        return _error(e)
