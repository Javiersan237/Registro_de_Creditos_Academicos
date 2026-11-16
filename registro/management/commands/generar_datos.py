"""Crea datos simulados para probar el prototipo (la guía prohíbe datos reales).

  python manage.py generar_datos
  python manage.py generar_datos --telefono 4881234567 --correo tu_correo@matehuala.tecnm.mx

--telefono/--correo se asignan SOLO al alumno de prueba 99660001 para recibir los avisos.
Los demás alumnos usan correos @ejemplo.test (dominio reservado, no se entregan) y sin teléfono.
"""
import random
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from registro import firma
from registro.context import GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS
from registro.models import CARRERAS, Alumno, Configuracion, Conferencia, Pregunta, Registro

PREGUNTAS_PYTHON = [
    ("¿Qué lenguaje se usó en la demostración principal?", ["Python", "Cobol", "Pascal"], 0),
    ("¿Qué problema resolvía el ejemplo?", ["Registrar asistencia", "Imprimir diplomas", "Reservar salas"], 0),
    ("¿Qué formato se usó para el archivo de salida?", ["CSV", "DOCX", "MP3"], 0),
    ("¿Cuántas personas intervenían en el flujo automatizado?", ["Menos que antes", "Más que antes", "Igual que antes"], 0),
    ("¿Qué herramienta se mencionó para las notificaciones?", ["Un bot", "Una carta", "Un fax"], 0),
]
PREGUNTAS_ENERGIA = [
    ("¿Qué fuente de energía fue el tema central?", ["Solar", "Carbón", "Diésel"], 0),
    ("¿Qué componente convierte la luz en electricidad?", ["Panel fotovoltaico", "Turbina de gas", "Caldera"], 0),
    ("¿Qué beneficio principal se mencionó?", ["Menos emisiones", "Más ruido", "Mayor consumo de agua"], 0),
    ("¿Dónde se instaló el caso de estudio?", ["En un techo escolar", "En una mina", "En un barco"], 0),
    ("¿Qué se mide en kilowatts-hora?", ["Energía", "Temperatura", "Presión"], 0),
]


class Command(BaseCommand):
    help = "Genera padrón, usuarios, conferencias y registros simulados."

    def add_arguments(self, parser):
        parser.add_argument("--telefono", default="", help="Teléfono (10 dígitos) del alumno de prueba 99660001")
        parser.add_argument("--correo", default="", help="Correo del alumno de prueba 99660001")
        parser.add_argument("--password", default="Renueva2026!", help="Contraseña de los usuarios de demostración")
        parser.add_argument("--alumnos", type=int, default=60)
        parser.add_argument("--sin-historial", action="store_true", help="No crear registros de la conferencia de ayer")

    def handle(self, *args, **o):
        random.seed(2026)
        Configuracion.actual()

        # Roles y usuarios (NFR-07)
        grupos = {n: Group.objects.get_or_create(name=n)[0] for n in (GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS)}
        usuarios = {}
        for username, nombre, grupo in [("comite", "Comité Demo", GRUPO_COMITE),
                                         ("profesor", "Profesor Demo 03", GRUPO_PROFESOR),
                                         ("servicios", "Servicios Escolares Demo", GRUPO_SERVICIOS)]:
            u, _ = User.objects.get_or_create(username=username)
            u.first_name = nombre
            u.set_password(o["password"])
            u.save()
            u.groups.set([grupos[grupo]])
            usuarios[username] = u
        admin, _ = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
        admin.is_staff = admin.is_superuser = True
        admin.set_password(o["password"])
        admin.save()

        # Padrón simulado (FR-03)
        claves = [c for c, _ in CARRERAS]
        for i in range(1, o["alumnos"] + 1):
            nc = f"9966{i:04d}"
            Alumno.objects.update_or_create(no_control=nc, defaults=dict(
                nombre="Alumno", apellidos=f"Demo {i:03d}", carrera=claves[(i - 1) % len(claves)],
                semestre=random.choice([1, 3, 5, 7]), grupo=random.choice(["A", "B"]),
                telefono="", correo=f"l{nc}@ejemplo.test"))
        prueba = Alumno.objects.get(pk="99660001")
        prueba.nombre, prueba.apellidos = "Usuario", "Prueba Renueva"
        if o["telefono"]:
            prueba.telefono = o["telefono"]
        if o["correo"]:
            prueba.correo = o["correo"]
        prueba.save()

        # Conferencias: ayer (cerrada, con historial) y hoy (activa ahora mismo)
        ahora = timezone.localtime()
        inicio_hoy = (ahora - timedelta(minutes=10)).replace(second=0, microsecond=0)
        fin_hoy = inicio_hoy + timedelta(minutes=90)
        if fin_hoy.date() != inicio_hoy.date():  # cerca de medianoche
            inicio_hoy, fin_hoy = inicio_hoy.replace(hour=0, minute=0), inicio_hoy.replace(hour=23, minute=0)
        ayer = (ahora - timedelta(days=1)).date()

        c_ayer, nueva_ayer = Conferencia.objects.get_or_create(
            nombre="Innovación en energías limpias", fecha=ayer,
            defaults=dict(hora_inicio=ahora.replace(hour=11, minute=0).time(),
                          hora_fin=ahora.replace(hour=12, minute=30).time(), creditos=1,
                          profesor=usuarios["profesor"], creada_por=usuarios["comite"], lugar="Sala audiovisual"))
        c_hoy, nueva_hoy = Conferencia.objects.get_or_create(
            nombre="Automatización de procesos con Python", fecha=inicio_hoy.date(),
            defaults=dict(hora_inicio=inicio_hoy.time(), hora_fin=fin_hoy.time(), creditos=1,
                          profesor=usuarios["profesor"], creada_por=usuarios["comite"], lugar="Gimnasio auditorio"))
        for c, preguntas, nueva in [(c_ayer, PREGUNTAS_ENERGIA, nueva_ayer), (c_hoy, PREGUNTAS_PYTHON, nueva_hoy)]:
            if nueva:
                for n, (t, ops, ok) in enumerate(preguntas, 1):
                    Pregunta.objects.create(conferencia=c, orden=n, texto=t, opciones=ops, correcta=ok)

        # Historial simulado de ayer: mezcla de válidos y no válidos, para que el tablero tenga datos
        if nueva_ayer and not o["sin_historial"]:
            from registro.servicios import registrar_por_qr
            import uuid
            from django.test.utils import override_settings
            m0 = firma.minuto_de(c_ayer.inicio_dt())
            with override_settings(NOTIF_ASYNC=False):
                for i in range(1, int(o["alumnos"] * 0.7) + 1):
                    nc = f"9966{i:04d}"
                    perfil = 1.0 if i == 1 else random.random()  # el alumno de prueba asistió bien ayer
                    correctas = [p.correcta for p in c_ayer.preguntas.all()]
                    if perfil < 0.08:      # respondió muy rápido
                        resp, t = correctas, 40
                    elif perfil < 0.16:    # menos de 50 %
                        resp, t = [(x + 1) % 3 for x in correctas[:3]] + correctas[3:], 150
                    else:
                        resp, t = correctas[:4] + [random.choice([0, 1])], random.randint(110, 280)
                    registrar_por_qr(uuid=uuid.uuid4(), token=firma.firmar(c_ayer, m0 + random.randint(5, 80)),
                                     no_control=nc, respuestas=resp, tiempo_seg=t)
            from registro.models import Aviso
            Aviso.objects.all().delete()  # los avisos del historial simulado no se envían

        self.stdout.write(self.style.SUCCESS("Datos simulados listos."))
        self.stdout.write(f"  Usuarios: comite, profesor, servicios, admin · contraseña: {o['password']}")
        self.stdout.write(f"  Alumnos: {Alumno.objects.count()} (prueba: 99660001 -> {prueba.correo} / {prueba.telefono or 'sin teléfono'})")
        self.stdout.write(f"  Conferencia activa: «{c_hoy.nombre}» {c_hoy.hora_inicio:%H:%M}–{c_hoy.hora_fin:%H:%M} (id {c_hoy.pk})")
        self.stdout.write(f"  Registros: {Registro.objects.count()}")
