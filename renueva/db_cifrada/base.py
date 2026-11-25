"""Backend de Django: SQLite cifrado con SQLCipher (AES-256) · versión del salón, 24 nov 2026.

Es el backend sqlite3 de Django con otra librería (sqlcipher3, compatible) y la llave puesta antes de cualquier
otra instrucción. Todo el archivo queda cifrado: tablas, nombres, teléfonos, registros, respuestas y los vínculos
entre ellos. Sin la llave el archivo es ilegible, y si alguien cambia bytes, SQLCipher lo detecta (HMAC por página).

La llave (64 caracteres hexadecimales = 32 bytes) llega en DB_CLAVE desde la bóveda del lanzador; nunca va en disco.
"""
import datetime
from collections.abc import Mapping
from itertools import tee
import decimal

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.sqlite3 import base as sqlite_base
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from sqlcipher3 import dbapi2 as Database

# Los mismos convertidores y adaptadores que Django registra para sqlite3
Database.register_converter("bool", b"1".__eq__)
Database.register_converter("date", sqlite_base.decoder(parse_date))
Database.register_converter("time", sqlite_base.decoder(parse_time))
Database.register_converter("datetime", sqlite_base.decoder(parse_datetime))
Database.register_converter("timestamp", sqlite_base.decoder(parse_datetime))
Database.register_adapter(decimal.Decimal, str)
Database.register_adapter(datetime.date, sqlite_base.adapt_date)
Database.register_adapter(datetime.datetime, sqlite_base.adapt_datetime)


def pragma_llave(clave):
    clave = (clave or "").strip().lower()
    if len(clave) != 64 or any(c not in "0123456789abcdef" for c in clave):
        raise ImproperlyConfigured("DB_CLAVE debe tener 64 caracteres hexadecimales.")
    return f"PRAGMA key = \"x'{clave}'\""   # llave en bruto: sin derivación extra (ya viene aleatoria)


class DatabaseWrapper(sqlite_base.DatabaseWrapper):
    Database = Database

    def get_new_connection(self, conn_params):
        conn = Database.connect(**conn_params)
        conn.execute(pragma_llave(self.settings_dict.get("CLAVE", "")))
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()   # falla aquí si la llave no es la correcta
        sqlite_base.register_functions(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        for init_command in self.init_commands:
            if init_command := init_command.strip():
                conn.execute(init_command)
        return conn


class CursorCifrado(Database.Cursor):
    """El mismo traductor de parámetros de Django (%s → ?, %(x)s → :x), sobre el cursor de sqlcipher3."""

    def execute(self, query, params=None):
        if params is None:
            return super().execute(query)
        nombres = list(params) if isinstance(params, Mapping) else None
        return super().execute(self.convert_query(query, param_names=nombres), params)

    def executemany(self, query, param_list):
        peek, param_list = tee(iter(param_list))
        primero = next(peek, None)
        nombres = list(primero) if (primero and isinstance(primero, Mapping)) else None
        return super().executemany(self.convert_query(query, param_names=nombres), param_list)

    convert_query = sqlite_base.SQLiteCursorWrapper.convert_query


def _create_cursor(self, name=None):
    return self.connection.cursor(factory=CursorCifrado)


DatabaseWrapper.create_cursor = sqlite_base.async_unsafe(_create_cursor)
