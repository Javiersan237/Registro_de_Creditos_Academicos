"""CU-07 3a: reintenta los avisos que fallaron (o quedaron pendientes)."""
from django.core.management.base import BaseCommand

from registro.notificaciones import reintentar_errores


class Command(BaseCommand):
    help = "Reintenta los avisos con error o pendientes."

    def handle(self, *args, **o):
        self.stdout.write(f"Avisos reintentados: {reintentar_errores()}")
