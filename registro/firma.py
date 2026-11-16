"""QR firmado que cambia cada minuto (FR-02, RN-11, NFR-07).

Formato del token:  <id_conferencia>.<minuto>.<firma>
  - minuto: minutos desde 1970 (UTC). Es la «hora que lleva el QR».
  - firma: HMAC-SHA256 con una clave que nunca sale del servidor.
El QR no lleva datos personales (E3 §3.3).
"""
import hashlib
import hmac
import time
from datetime import datetime, timezone as dt_tz

from django.conf import settings


class TokenInvalido(Exception):
    pass


def _firma(conferencia, minuto):
    clave = (settings.QR_SIGNING_KEY + conferencia.clave).encode()
    msg = f"{conferencia.pk}.{minuto}".encode()
    return hmac.new(clave, msg, hashlib.sha256).hexdigest()[:20]


def minuto_de(dt):
    return int(dt.timestamp() // 60)


def minuto_actual():
    return int(time.time() // 60)


def minuto_a_fecha(minuto):
    return datetime.fromtimestamp(minuto * 60, tz=dt_tz.utc)


def firmar(conferencia, minuto):
    return f"{conferencia.pk}.{minuto}.{_firma(conferencia, minuto)}"


def minutos_de_ventana(conferencia):
    """Un minuto por cada minuto de la ventana de registro (inicio → fin + tolerancia)."""
    return range(minuto_de(conferencia.inicio_dt()), minuto_de(conferencia.cierre_dt()) + 1)


def paquete_qr(conferencia):
    """FR-02: un token firmado distinto por cada minuto de la ventana."""
    return [(m, firmar(conferencia, m)) for m in minutos_de_ventana(conferencia)]


def leer(token):
    """Separa el token sin verificarlo. Devuelve (id_conferencia, minuto)."""
    try:
        cid, minuto, firma = token.split(".")
        return int(cid), int(minuto)
    except (ValueError, AttributeError):
        raise TokenInvalido("El código QR no es válido. Vuelve a escanearlo.")


def verificar(token):
    """Comprueba la firma. Devuelve (conferencia, minuto). Un QR alterado se rechaza."""
    from .models import Conferencia

    cid, minuto = leer(token)
    try:
        conferencia = Conferencia.objects.get(pk=cid)
    except Conferencia.DoesNotExist:
        raise TokenInvalido("La conferencia de este QR no existe.")
    esperado = firmar(conferencia, minuto)
    if not hmac.compare_digest(esperado, token):
        raise TokenInvalido("El código QR fue alterado o no es de Renueva TI.")
    return conferencia, minuto
