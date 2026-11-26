"""CU-07 3a: reintenta los avisos que fallaron y los pendientes de hace más de 10 minutos."""
from django.core.management.base import BaseCommand

from registro.notificaciones import reintentar_errores


class Command(BaseCommand):
    help = "Reintenta los avisos con error y los pendientes de hace más de 10 minutos."

    def handle(self, *args, **o):
        self.stdout.write(f"Avisos reintentados: {reintentar_errores()}")
