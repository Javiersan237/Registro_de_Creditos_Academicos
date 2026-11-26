"""NFR-08: restaura un respaldo creado con `respaldar`.

  python manage.py restaurar respaldo_20261116_120000.sqlite3      (lo busca en <carpeta de datos>/backups)
  python manage.py restaurar D:\\otra\\carpeta\\respaldo.sqlite3     (ruta completa, cualquier unidad)
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from registro.respaldo import copiar_base, carpeta_respaldos


class Command(BaseCommand):
    help = "Reemplaza la base actual con el respaldo indicado (detén el servidor antes)."

    def add_arguments(self, parser):
        parser.add_argument("archivo")

    def handle(self, *args, **o):
        archivo = Path(o["archivo"])
        if not archivo.is_absolute():
            archivo = carpeta_respaldos() / archivo
        if not archivo.exists():
            raise CommandError(f"No existe el respaldo: {archivo}")
        try:
            copiar_base(archivo, hacia_respaldo=False)
        except Exception as e:   # llave distinta o archivo dañado: la base actual no se toca
            raise CommandError(f"No se pudo restaurar desde {archivo}: {e}")
        self.stdout.write(self.style.SUCCESS(f"Base restaurada desde {archivo}"))
