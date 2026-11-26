"""API REST del E3 §3.5 (vistas JSON de Django).

Las rutas del alumno no usan sesión: se protegen con el QR firmado y, para
consultar el estado, con un código de 6 dígitos enviado al correo (FR-16).
"""
import json
import uuid as uuidlib
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import firma, notificaciones, validacion
from .models import CodigoConsulta, Configuracion, Conferencia, Registro
from .seguridad import limitar
from .servicios import ErrorRegistro, buscar_alumno, registrar_por_qr, verificar_nip


def _json(request):
    try:
        datos = json.loads(request.body or b"{}")
    except ValueError:
        datos = None
    if not isinstance(datos, dict):
        raise ErrorRegistro("La solicitud no tiene un formato válido.")
    return datos


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
    No incluye respuestas correctas, ni la clave de firma, ni datos de alumnos: antes llevaba el padrón como
    hash del número de control, pero 8 dígitos se adivinan en segundos. Sin internet el alumno no ve su nombre
    parcial; su NIP se verifica en el servidor al sincronizar."""
    c = get_object_or_404(Conferencia, pk=pk)
    cfg = Configuracion.actual()
    preguntas = list(c.preguntas.all())
    return JsonResponse({
        "id": c.pk, "nombre": c.nombre, "lugar": c.lugar, "fecha": f"{c.fecha:%d/%m/%Y}",
        "horario": f"{c.hora_inicio:%H:%M} a {c.hora_fin:%H:%M} h",
        "inicio": int(c.inicio_dt().timestamp() // 60), "cierre": int(c.cierre_dt(cfg).timestamp() // 60),
        "preguntas": [{"texto": p.texto, "opciones": p.opciones} for p in preguntas],
        # D-13: la app muestra cuánto falta y no deja enviar antes del tiempo mínimo (RN-15)
        "tiempo_minimo_seg": validacion.tiempo_minimo(len(preguntas), cfg),
        "descargado": timezone.now().isoformat(),
    })


@csrf_exempt
@require_POST
@limitar("identificar", 30, 600)   # 30 intentos de NIP cada 10 min por dispositivo
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
@limitar("registros", 120, 600)    # un celular sincroniza pocos registros; 120 deja margen a la laptop (modo B)
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
            nip_verificado=firma.firma_sync_valida(u, d.get("sync_firma")), telefono=d.get("telefono"))
        return JsonResponse({"ok": True, "nuevo": nuevo, "duplicado": duplicado,
                             "registro": _registro_json(registro)}, status=201 if nuevo else 200)
    except ErrorRegistro as e:
        return _error(e)
    except (ValueError, TypeError):
        # Dato mal formado (p. ej. tiempo_seg="a"): 400 para que el celular lo descarte; un 500 lo dejaría
        # atorado en la cola bloqueando a los registros que vienen detrás.
        return _error(ErrorRegistro("El registro llegó con datos mal formados y no se puede guardar."))


@csrf_exempt
@require_POST
@limitar("codigo", 5, 600)          # cada código manda un WhatsApp: pocos por dispositivo
def pedir_codigo(request):
    """FR-16, paso 1: envía un código de 6 dígitos al correo institucional
    (en la versión del salón, sin correo, al WhatsApp que el alumno escribió)."""
    try:
        alumno = buscar_alumno(_json(request).get("no_control"))
        reciente = CodigoConsulta.objects.filter(alumno=alumno, usado=False,
                                                 expira__gt=timezone.now() + timedelta(minutes=9)).exists()
        if reciente:
            raise ErrorRegistro("Ya te enviamos un código hace menos de un minuto. Revisa tus mensajes "
                                "o espera un momento.", 429)
        if "correo" in settings.NOTIF_CANALES:
            canal, destino = "correo", f"tu correo {alumno.correo_enmascarado()} (revisa también la carpeta de spam)"
        elif alumno.telefono:
            canal, destino = "whatsapp", f"tu WhatsApp {alumno.telefono_enmascarado()}"
        else:
            raise ErrorRegistro("No tenemos un teléfono tuyo todavía. Regístrate primero en una conferencia "
                                "y escribe ahí tu número.", 404)
        codigo = CodigoConsulta.nuevo(alumno)
        asunto, texto = notificaciones.msg_codigo(alumno, codigo.codigo)
        notificaciones.notificar(alumno, "codigo", asunto, texto, canales=(canal,))
        return JsonResponse({"ok": True, "destino": destino, "correo": alumno.correo_enmascarado()})
    except ErrorRegistro as e:
        return _error(e)


@csrf_exempt
@require_POST
@limitar("estado", 20, 600)
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
            raise ErrorRegistro("El código no coincide. Revisa el mensaje más reciente e inténtalo de nuevo.", 403)
        codigo.usado = True
        codigo.save(update_fields=["usado"])
        regs = alumno.registros.select_related("conferencia", "lote")
        return JsonResponse({"ok": True, "nombre_parcial": alumno.nombre_parcial(),
                             "registros": [_registro_json(r) for r in regs]})
    except ErrorRegistro as e:
        return _error(e)
