"""Revisa los sellos de los registros y la cadena de la bitácora. Sale con código 1 si encuentra alteraciones.

  python manage.py verificar_integridad [--json]
"""
import json
import sys

from django.core.management.base import BaseCommand

from registro.integridad import verificar
from registro.models import Bitacora


class Command(BaseCommand):
    help = "Verifica que nadie haya modificado registros o bitácora fuera de la app."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **o):
        r = verificar()
        Bitacora.registrar(None, "Verificación de integridad", "Base de datos",
                           "Sin alteraciones" if r["ok"] else f"{len(r['problemas'])} problema(s)")
        if o["json"]:
            self.stdout.write("INTEGRIDAD " + json.dumps(r, ensure_ascii=False))
        else:
            self.stdout.write(f"Registros: {r['registros']} · Bitácora: {r['bitacora']} · Sin sello: {r['sin_sello']}")
            for p in r["problemas"]:
                self.stdout.write(self.style.ERROR("  " + p))
            self.stdout.write(self.style.SUCCESS("Sin alteraciones.") if r["ok"] else self.style.ERROR("ALTERADO"))
        if not r["ok"]:
            sys.exit(1)
