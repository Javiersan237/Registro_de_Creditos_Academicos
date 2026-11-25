"""Anota en la bitácora una acción del administrador de la laptop (lanzador del salón)."""
from django.core.management.base import BaseCommand

from registro.models import Bitacora


class Command(BaseCommand):
    help = "Agrega una entrada a la bitácora encadenada."

    def add_arguments(self, parser):
        parser.add_argument("accion")
        parser.add_argument("detalle", nargs="?", default="")

    def handle(self, *args, **o):
        Bitacora.registrar(None, o["accion"], "Laptop del salón", o["detalle"])
