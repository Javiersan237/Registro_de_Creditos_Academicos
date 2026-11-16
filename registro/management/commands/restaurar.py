"""NFR-08: restaura un respaldo creado con `respaldar`.

  python manage.py restaurar backups/respaldo_20261116_120000.sqlite3
"""
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Reemplaza la base actual con el respaldo indicado (detén el servidor antes)."

    def add_arguments(self, parser):
        parser.add_argument("archivo")

    def handle(self, *args, **o):
        archivo = settings.BASE_DIR / o["archivo"] if not o["archivo"].startswith(("/", "C:", "c:")) else o["archivo"]
        try:
            origen = sqlite3.connect(f"file:{archivo}?mode=ro", uri=True)
        except sqlite3.Error as e:
            raise CommandError(f"No se pudo abrir el respaldo: {e}")
        destino = sqlite3.connect(settings.DATABASES["default"]["NAME"])
        with destino:
            origen.backup(destino)
        destino.close()
        origen.close()
        self.stdout.write(self.style.SUCCESS(f"Base restaurada desde {archivo}"))
