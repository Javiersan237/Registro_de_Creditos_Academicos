"""Integridad de los datos (versión del salón, 24 nov 2026).

- Cada registro de asistencia lleva un SELLO: HMAC-SHA256 de sus campos con una clave del servidor.
  Si alguien abre la base de datos y cambia, por ejemplo, «válido» o las respuestas, el sello ya no coincide.
  El sello no cubre el lote ni la sincronización, que cambian de forma legítima con el flujo normal.
- La bitácora es una CADENA: cada entrada guarda la huella de la anterior. Borrar, cambiar o intercalar
  una entrada rompe la cadena desde ese punto.
Sin la clave (que en la laptop va cifrada en la bóveda) no se puede fabricar un sello válido.
"""
import hashlib
import hmac
import json

from django.conf import settings


def _clave():
    return settings.INTEGRIDAD_KEY.encode()


def _ms(dt):
    return None if dt is None else round(dt.timestamp() * 1000)


def _firmar(datos):
    texto = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hmac.new(_clave(), texto.encode(), hashlib.sha256).hexdigest()


def sello_registro(r):
    return _firmar({
        "uuid": str(r.uuid), "folio": r.folio, "alumno": r.alumno_id, "conferencia": r.conferencia_id,
        "token": r.token, "minuto_qr": _ms(r.minuto_qr), "respuestas": r.respuestas, "aciertos": r.aciertos,
        "total": r.total, "porcentaje": round(float(r.porcentaje), 3), "tiempo_seg": r.tiempo_seg,
        "capturado_en": _ms(r.capturado_en), "origen": r.origen, "motivo_asistido": r.motivo_asistido,
        "registrado_por": r.registrado_por_id, "valido": bool(r.valido), "motivo": r.motivo,
        "recibido": _ms(r.recibido),
    })


def huella_bitacora(b, anterior):
    return _firmar({"anterior": anterior, "id": b.pk, "usuario": b.usuario_id, "accion": b.accion,
                    "objeto": b.objeto, "detalle": b.detalle, "fecha": _ms(b.fecha)})


def verificar():
    """Revisa todos los sellos y la cadena. Devuelve un resumen con los problemas encontrados."""
    from .models import Bitacora, Registro

    problemas, sin_sello = [], 0
    registros = 0
    for r in Registro.objects.all().order_by("pk").iterator():
        registros += 1
        if not r.sello:
            sin_sello += 1
        elif not hmac.compare_digest(r.sello, sello_registro(r)):
            problemas.append(f"Registro {r.folio} (alumno {r.alumno_id}) fue modificado fuera de la app.")

    anterior, entradas, ids_previos = "", 0, None
    for b in Bitacora.objects.all().order_by("pk").iterator():
        entradas += 1
        if not b.huella:
            anterior = ""
            continue
        if b.huella_anterior != anterior:
            problemas.append(f"Bitácora: falta o se cambió una entrada antes de la #{b.pk} ({b.accion}).")
        if not hmac.compare_digest(b.huella, huella_bitacora(b, b.huella_anterior)):
            problemas.append(f"Bitácora: la entrada #{b.pk} ({b.accion}) fue modificada.")
        anterior = b.huella
    return {"ok": not problemas, "registros": registros, "sin_sello": sin_sello,
            "bitacora": entradas, "problemas": problemas}
