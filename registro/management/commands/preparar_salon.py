"""Versión del salón: deja lista la demostración en una laptop.

  python manage.py preparar_salon

1. Genera los datos simulados (usuarios, padrón y la conferencia de ayer con historial).
2. Crea la conferencia de demostración «Renueva TI: así automatizamos tus créditos del Congreso»,
   abierta desde ahora hasta las 23:59 de hoy, con preguntas sobre el propio proyecto.
3. Muestra los números de control de prueba y sus NIP para repartirlos en el salón.

Se puede correr cada vez que se prepara una presentación: reemplaza solo la conferencia de hoy del salón.
"""
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from registro.models import Conferencia, Pregunta

NOMBRE = "Renueva TI: así automatizamos tus créditos del Congreso"

# (pregunta, opciones, índice de la correcta). La correcta no siempre es la primera.
PREGUNTAS_SALON = [
    ("¿Qué problema resuelve este sistema?",
     ["Reservar el auditorio para las conferencias",
      "Registrar la asistencia al Congreso Académico y convertirla en créditos complementarios",
      "Imprimir las constancias de los ponentes"], 1),
    ("¿Con qué tecnología se construyó el servidor?",
     ["Django, un framework de Python", "Laravel, un framework de PHP", "WordPress"], 0),
    ("¿Por qué el QR de la conferencia cambia cada minuto?",
     ["Para que se vea más moderno",
      "Para ahorrar batería en el celular",
      "Para que nadie se registre con la foto de un QR viejo o desde fuera de la sala"], 2),
    ("¿Qué pasa si en el auditorio no hay internet?",
     ["El registro se guarda en el celular y se envía solo cuando vuelve la señal",
      "El registro se pierde y hay que firmar la lista en papel",
      "La app no abre"], 0),
    ("¿En qué formato recibe Servicios Escolares el archivo para cargar al SIIC?",
     ["PDF escaneado", "CSV, listo para cargar", "Una foto de la lista"], 1),
    ("¿Por qué pedimos el NIP además del número de control?",
     ["Para calcular el promedio del alumno",
      "Para que nadie pueda registrar a un compañero solo con saber su número de control",
      "Porque el SIIC lo exige para imprimir"], 1),
]


class Command(BaseCommand):
    help = "Prepara la demostración del salón: datos simulados + conferencia sobre el proyecto abierta hasta las 23:59."

    def add_arguments(self, parser):
        parser.add_argument("--sin-datos", action="store_true",
                            help="No regenerar los datos simulados (solo la conferencia del salón)")
        parser.add_argument("--lugar", default="Salón de clases")
        parser.add_argument("--password", default="", help="Contraseña de los usuarios del personal")

    def handle(self, *args, **o):
        if not o["sin_datos"]:
            extra = ["--password", o["password"]] if o["password"] else []
            call_command("generar_datos", *extra, stdout=self.stdout)

        from django.contrib.auth.models import User
        ahora = timezone.localtime()
        inicio = (ahora - timedelta(minutes=5)).replace(second=0, microsecond=0)
        if inicio.date() != ahora.date():
            inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=23, minute=59, second=0, microsecond=0)

        # Una sola conferencia del salón por día; si ya existe sin registros, se reemplaza
        for c in Conferencia.objects.filter(nombre=NOMBRE, fecha=ahora.date()):
            if c.registros.exists():
                c.hora_fin = fin.time()
                c.save(update_fields=["hora_fin"])
                conf = c
                break
            c.delete()
        else:
            conf = Conferencia.objects.create(
                nombre=NOMBRE, fecha=ahora.date(), hora_inicio=inicio.time(), hora_fin=fin.time(), creditos=1,
                lugar=o["lugar"], profesor=User.objects.filter(username="profesor").first(),
                creada_por=User.objects.filter(username="comite").first())
            for n, (t, ops, ok) in enumerate(PREGUNTAS_SALON, 1):
                Pregunta.objects.create(conferencia=conf, orden=n, texto=t, opciones=ops, correcta=ok)

        self.stdout.write(self.style.SUCCESS("\nSalón listo."))
        self.stdout.write(f"  Conferencia: «{conf.nombre}» {conf.hora_inicio:%H:%M}–{conf.hora_fin:%H:%M} (id {conf.pk})")
        self.stdout.write("  Números de prueba para los compañeros (número de control → NIP):")
        for i in range(2, 52):
            nc = f"9966{i:04d}"
            self.stdout.write(f"    {nc} → {nc[:3:-1]}")
        self.stdout.write("  Cada alumno escribe su propio WhatsApp al registrarse.")
