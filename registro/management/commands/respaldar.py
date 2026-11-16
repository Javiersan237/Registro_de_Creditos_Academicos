"""NFR-08: respaldo de la base de datos (se programa a diario con el Programador de tareas de Windows o cron).

  python manage.py respaldar
"""
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Crea una copia consistente de la base SQLite en la carpeta backups/."

    def handle(self, *args, **o):
        carpeta = settings.BASE_DIR / "backups"
        carpeta.mkdir(exist_ok=True)
        destino = carpeta / f"respaldo_{timezone.localtime():%Y%m%d_%H%M%S}.sqlite3"
        origen = sqlite3.connect(settings.DATABASES["default"]["NAME"])
        copia = sqlite3.connect(destino)
        with copia:
            origen.backup(copia)   # copia en caliente, segura aunque haya escrituras
        copia.close()
        origen.close()
        self.stdout.write(self.style.SUCCESS(f"Respaldo creado: {destino}"))
