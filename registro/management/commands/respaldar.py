"""NFR-08: respaldo de la base de datos (se programa a diario con el Programador de tareas de Windows o cron).

  python manage.py respaldar

Usa la conexión de Django, que ya trae la llave: funciona igual con la base normal y con la base cifrada
(SQLCipher) de la laptop del salón. El respaldo de una base cifrada queda cifrado con la misma llave.
Se guarda en <carpeta de datos>/backups (en la laptop, %LOCALAPPDATA%\\RegistroCreditosTecNM\\backups).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from registro.respaldo import copiar_base, carpeta_respaldos


class Command(BaseCommand):
    help = "Crea una copia consistente de la base de datos en la carpeta de datos/backups."

    def handle(self, *args, **o):
        carpeta = carpeta_respaldos()
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"respaldo_{timezone.localtime():%Y%m%d_%H%M%S}.sqlite3"
        copiar_base(destino, hacia_respaldo=True)
        self.stdout.write(self.style.SUCCESS(f"Respaldo creado: {destino}"))
