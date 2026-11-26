"""Avisos al alumno por correo y WhatsApp (FR-13, FR-14, FR-15, FR-16, FR-27).

- Cada aviso se guarda en la tabla Aviso con su estado y su error (CU-07 3a).
- El correo es el canal garantizado; WhatsApp es adicional (riesgo R4).
- En NOTIF_MODO=prueba solo se envía a la lista blanca; el resto queda «simulado».
"""
import logging
import threading
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from django.utils.html import escape

from .models import Aviso, Configuracion

log = logging.getLogger("registro")

FIRMA = "Renueva TI · Renovando Mundos, Renovándote a ti\nEste aviso es parte de un prototipo escolar con datos simulados."
# Encabezado y pie de WhatsApp (versión del salón): quién escribe y por qué, para que no parezca spam.
WA_ENCABEZADO = "TecNM · Instituto Tecnológico de Matehuala"
WA_PIE = ("_Prototipo escolar del registro de créditos (desarrollado por Renueva TI). "
          "Recibes este mensaje porque escribiste este número al registrar tu asistencia._")
_wa_candado = threading.Lock()
_wa_ultimo = [0.0]


# ---------------------------------------------------------------- mensajes
def msg_registro_no_valido(registro):
    cfg = Configuracion.actual()
    return ("Tu registro no fue válido",
            f"Hola, {registro.alumno.nombre}.\n\n"
            f"Tu registro en la conferencia «{registro.conferencia.nombre}» (folio {registro.folio}) no fue válido.\n"
            f"Motivo: {registro.motivo}.\n\n"
            f"El cuestionario no se repite. Si crees que es un error, comunícate con: {cfg.contacto_encargado}.")


def msg_registro_recibido(registro):
    return ("Registramos tu asistencia",
            f"Hola, {registro.alumno.nombre}.\n\n"
            f"Recibimos tu registro en la conferencia «{registro.conferencia.nombre}».\n"
            f"Folio: {registro.folio}\nEstado: validado por el sistema.\n\n"
            f"Te avisaremos por aquí cuando tu crédito quede cargado en el SIIC.")


def msg_cargado(alumno, registros, con_credito):
    conferencias = ", ".join(f"«{r.conferencia.nombre}»" for r in registros)
    if con_credito:
        creditos = max(r.conferencia.creditos for r in registros)
        cuerpo = (f"Hola, {alumno.nombre}.\n\n"
                  f"¡Listo! Tu crédito de actividades complementarias por el Congreso Académico ya fue cargado en el SIIC.\n"
                  f"Conferencias: {conferencias}.\nCréditos: {creditos}.\n\n"
                  f"Puedes verlo en tu Kardex del SIIC.")
        return "Tu crédito ya está en el SIIC", cuerpo
    cuerpo = (f"Hola, {alumno.nombre}.\n\n"
              f"Tu asistencia a {conferencias} quedó registrada en el SIIC.\n"
              f"Puedes consultar el estado de tus registros cuando quieras en la app del registro de asistencia.")
    return "Tu asistencia quedó registrada en el SIIC", cuerpo


def msg_falla(alumno, registros, motivo):
    cfg = Configuracion.actual()
    conferencias = ", ".join(f"«{r.conferencia.nombre}»" for r in registros)
    return ("Hubo un problema al cargar tu registro",
            f"Hola, {alumno.nombre}.\n\n"
            f"Hubo un problema al cargar en el SIIC tu registro de {conferencias}.\n"
            f"Motivo: {motivo}.\n\n"
            f"No necesitas volver a registrarte. Para aclararlo, comunícate con: {cfg.contacto_encargado}.")


def msg_codigo(alumno, codigo):
    return ("Tu código para consultar tu estado",
            f"Hola, {alumno.nombre}.\n\nTu código para consultar el estado de tus registros es:\n\n"
            f"    {codigo}\n\nVence en 10 minutos. Si no lo pediste, ignora este mensaje.")


# ---------------------------------------------------------------- envío
def _permitido(aviso):
    canal, destino = aviso.canal, aviso.destino
    if canal not in settings.NOTIF_CANALES:
        return False
    if settings.NOTIF_MODO == "real":
        return True
    if canal == Aviso.CORREO:
        return destino.lower() in settings.NOTIF_LISTA_BLANCA_CORREOS
    if destino in settings.NOTIF_LISTA_BLANCA_TELEFONOS:
        return True
    # Versión del salón: el número que el propio alumno escribió (con su NIP verificado) sí recibe su aviso.
    al = aviso.alumno
    return settings.NOTIF_TELEFONO_ALUMNO and al.telefono_del_alumno and al.telefono == destino


def _html(asunto, texto):
    cuerpo = escape(texto).replace("\n", "<br>")
    return (
        '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #C7D0DC;border-radius:12px;overflow:hidden">'
        '<div style="background:#00102E;color:#fff;padding:14px 18px;font-size:18px;font-weight:bold">'
        'Renueva <span style="color:#2DCAE3">TI</span></div>'
        f'<div style="padding:18px;color:#00102E;font-size:15px;line-height:1.5"><h2 style="margin-top:0;font-size:18px">{escape(asunto)}</h2>{cuerpo}</div>'
        '<div style="background:#E9F1FA;padding:10px 18px;font-size:12px;color:#5A6475">'
        'Renovando Mundos, Renovándote a ti · Prototipo escolar con datos simulados</div></div>')


def _enviar_correo(aviso):
    texto = f"{aviso.contenido}\n\n--\n{FIRMA}"
    m = EmailMultiAlternatives(f"Renueva TI · {aviso.asunto}", texto, settings.DEFAULT_FROM_EMAIL, [aviso.destino])
    m.attach_alternative(_html(aviso.asunto, aviso.contenido), "text/html")
    m.send(fail_silently=False)


def _enviar_whatsapp(aviso):
    if not settings.WHATSAPP_ENABLED:
        raise RuntimeError("WhatsApp desactivado (WHATSAPP_ENABLED=0)")
    texto = f"*{WA_ENCABEZADO}*\n*{aviso.asunto}*\n\n{aviso.contenido}\n\n{WA_PIE}"
    with _wa_candado:  # un mensaje a la vez y con pausa: el número que envía no debe parecer spam
        espera = settings.WHATSAPP_PAUSA_SEG - (time.monotonic() - _wa_ultimo[0])
        if espera > 0:
            time.sleep(espera)
        try:
            _post_whatsapp(aviso, texto)
        finally:
            _wa_ultimo[0] = time.monotonic()


def _post_whatsapp(aviso, texto):
    r = requests.post(f"{settings.WHATSAPP_SERVICE_URL}/enviar",
                      json={"telefono": aviso.destino, "mensaje": texto},
                      headers={"x-token": settings.WHATSAPP_TOKEN}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Servicio de WhatsApp respondió {r.status_code}: {r.text[:200]}")


def despachar(aviso_id):
    """Envía un aviso y guarda el resultado. Nunca lanza excepción."""
    aviso = Aviso.objects.get(pk=aviso_id)
    if aviso.estado == Aviso.ENVIADO:
        return aviso
    if not _permitido(aviso):
        motivo = ("canal desactivado (NOTIF_CANALES)" if aviso.canal not in settings.NOTIF_CANALES
                  else "destino fuera de la lista blanca (modo prueba)")
        aviso.estado, aviso.error = Aviso.SIMULADO, f"No se envió: {motivo}."
        aviso.save(update_fields=["estado", "error"])
        return aviso
    aviso.intentos += 1
    try:
        (_enviar_correo if aviso.canal == Aviso.CORREO else _enviar_whatsapp)(aviso)
        aviso.estado, aviso.error, aviso.enviado = Aviso.ENVIADO, "", timezone.now()
    except Exception as e:  # se registra para reenvío manual (CU-07 3a)
        aviso.estado, aviso.error = Aviso.ERROR, str(e)[:500]
        log.warning("Aviso %s (%s) falló: %s", aviso.pk, aviso.canal, e)
    aviso.save(update_fields=["estado", "error", "enviado", "intentos"])
    return aviso


def _despachar_varios(ids):
    close_old_connections()
    try:
        for i in ids:
            despachar(i)
    finally:
        close_old_connections()


def notificar(alumno, tipo, asunto, contenido, canales=(Aviso.CORREO, Aviso.WHATSAPP)):
    """Crea los avisos y los envía (en segundo plano si NOTIF_ASYNC)."""
    ids = []
    for canal in canales:
        destino = alumno.correo if canal == Aviso.CORREO else alumno.telefono
        if not destino or canal not in settings.NOTIF_CANALES:
            continue
        ids.append(Aviso.objects.create(alumno=alumno, canal=canal, tipo=tipo, destino=destino,
                                        asunto=asunto, contenido=contenido).pk)
    if settings.NOTIF_ASYNC:
        threading.Thread(target=_despachar_varios, args=(ids,), daemon=True).start()
    else:
        for i in ids:
            despachar(i)
    return ids


def reintentar_errores():
    """Reintenta los avisos con error y los pendientes de hace más de 10 minutos. Los pendientes recientes siguen
    en la fila de envío (uno cada WHATSAPP_PAUSA_SEG): reenviarlos mandaría el mismo mensaje dos veces."""
    atorados = Q(estado=Aviso.PENDIENTE, creado__lt=timezone.now() - timedelta(minutes=10))
    ids = list(Aviso.objects.filter(Q(estado=Aviso.ERROR) | atorados).values_list("pk", flat=True))
    for i in ids:
        despachar(i)
    return len(ids)


def estado_whatsapp():
    if not settings.WHATSAPP_ENABLED:
        return {"activo": False, "detalle": "Desactivado en .env"}
    try:
        r = requests.get(f"{settings.WHATSAPP_SERVICE_URL}/estado",
                         headers={"x-token": settings.WHATSAPP_TOKEN}, timeout=4)
        return {"activo": r.ok and r.json().get("listo", False), "detalle": r.json().get("detalle", "")}
    except Exception as e:
        return {"activo": False, "detalle": f"Servicio no disponible: {e.__class__.__name__}"}
