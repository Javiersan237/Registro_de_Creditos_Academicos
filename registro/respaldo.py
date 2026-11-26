"""Respaldo y restauración de la base (NFR-08) con la conexión de Django.

La conexión de Django ya está abierta con la llave cuando la base va cifrada (renueva/db_cifrada), así que la
copia se hace con la API de respaldo de SQLite/SQLCipher: es consistente aunque haya escrituras en ese momento.
"""
from django.conf import settings
from django.db import connection


def carpeta_respaldos():
    return settings.DATOS_DIR / "backups"


def _abrir(ruta):
    """Abre otro archivo con la misma librería y, si la base va cifrada, con la misma llave."""
    otra = connection.Database.connect(str(ruta))
    clave = settings.DATABASES["default"].get("CLAVE")
    if clave:
        from renueva.db_cifrada.base import pragma_llave
        otra.execute(pragma_llave(clave))
    return otra


def copiar_base(ruta, hacia_respaldo):
    """hacia_respaldo=True: base actual → archivo. False: archivo → base actual."""
    connection.ensure_connection()
    otra = _abrir(ruta)
    try:
        if hacia_respaldo:
            connection.connection.backup(otra)
        else:
            otra.execute("SELECT count(*) FROM sqlite_master").fetchone()   # falla aquí si la llave no coincide
            otra.backup(connection.connection)
    finally:
        otra.close()
