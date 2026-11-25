"""Modelo de datos del E3, sección 3.4."""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

CARRERAS = [
    ("SIS", "Ing. en Sistemas Computacionales"),
    ("CIV", "Ing. Civil"),
    ("IND", "Ing. Industrial"),
    ("GES", "Ing. en Gestión Empresarial"),
    ("CON", "Lic. en Contaduría"),
]
CARRERAS_DICT = dict(CARRERAS)

ocho_digitos = RegexValidator(r"^\d{8}$", "El número de control debe tener 8 dígitos.")
diez_digitos = RegexValidator(r"^\d{10}$", "El teléfono debe tener 10 dígitos.")


class Configuracion(models.Model):
    """Reglas de negocio como parámetros (mantenibilidad, E3 §6.3): RN-11, RN-13, RN-14, RN-15, RN-16."""

    tolerancia_min = models.PositiveIntegerField(
        "Tolerancia después del fin (min)", default=15, help_text="RN-11")
    porcentaje_minimo = models.PositiveIntegerField(
        "Aciertos mínimos (%)", default=50, validators=[MaxValueValidator(100)], help_text="RN-14")
    segundos_por_pregunta = models.PositiveIntegerField(
        "Segundos mínimos por pregunta", default=20, help_text="RN-15")
    tiempo_minimo_tope_seg = models.PositiveIntegerField(
        "Tope del tiempo mínimo (s)", default=300,
        help_text="RN-15: el tiempo mínimo exigido nunca pasa de 5 minutos.")
    conferencias_para_credito = models.PositiveIntegerField(
        "Conferencias válidas para el crédito", default=2, help_text="RN-13 (no se muestra al alumno)")
    contacto_encargado = models.CharField(
        "Contacto del encargado de captura", max_length=200,
        default="Encargado de captura del SIIC, Servicios Escolares (contacto simulado)",
        help_text="RN-16")

    class Meta:
        verbose_name = "Configuración de reglas"
        verbose_name_plural = "Configuración de reglas"

    def __str__(self):
        return "Reglas de validación"

    @classmethod
    def actual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Alumno(models.Model):
    """Padrón (FR-03). En el prototipo todos los datos son simulados."""

    no_control = models.CharField("Número de control", max_length=8, primary_key=True,
                                  validators=[ocho_digitos])
    nombre = models.CharField(max_length=80)
    apellidos = models.CharField(max_length=120)
    carrera = models.CharField(max_length=3, choices=CARRERAS)
    semestre = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(14)])
    grupo = models.CharField(max_length=10)
    telefono = models.CharField(max_length=10, blank=True, validators=[diez_digitos])
    telefono_del_alumno = models.BooleanField(
        "Teléfono escrito por el alumno", default=False,
        help_text="El alumno lo escribió al registrarse con su NIP (versión del salón)")
    correo = models.EmailField("Correo institucional")
    # NIP de 4 dígitos (el mismo del SIIC). Nunca se guarda en claro: solo su HMAC con la clave del servidor.
    nip_hash = models.CharField("NIP (hash)", max_length=64, blank=True, editable=False)
    nip_intentos = models.PositiveSmallIntegerField(default=0, editable=False)
    nip_bloqueado_hasta = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["no_control"]

    def _hash_nip(self, nip):
        clave = settings.NIP_KEY.encode()
        return hmac.new(clave, f"{self.no_control}:{nip}".encode(), hashlib.sha256).hexdigest()

    def set_nip(self, nip):
        nip = str(nip or "").strip()
        if not (nip.isdigit() and len(nip) == 4):
            raise ValidationError("El NIP debe tener 4 dígitos.")
        self.nip_hash, self.nip_intentos, self.nip_bloqueado_hasta = self._hash_nip(nip), 0, None

    def nip_coincide(self, nip):
        nip = str(nip or "").strip()
        return (bool(self.nip_hash) and nip.isdigit() and len(nip) == 4
                and hmac.compare_digest(self.nip_hash, self._hash_nip(nip)))

    def __str__(self):
        return f"{self.no_control} · {self.nombre_completo}"

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellidos}"

    def nombre_parcial(self):
        """FR-28: «Hola, M* S*». Solo iniciales, para que el alumno confirme que es él."""
        partes = [self.nombre.split()[0] if self.nombre else "", self.apellidos.split()[0] if self.apellidos else ""]
        return " ".join(f"{p[0].upper()}*" for p in partes if p)

    def telefono_enmascarado(self):
        t = self.telefono or ""
        return f"{t[:3]} *** **{t[-2:]}" if len(t) == 10 else ""

    def correo_enmascarado(self):
        usuario, _, dominio = self.correo.partition("@")
        return f"{usuario[:2]}***@{dominio}"


class Conferencia(models.Model):
    nombre = models.CharField(max_length=160)
    lugar = models.CharField(max_length=80, default="Auditorio")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    creditos = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(2)], help_text="RN-03: máximo 2")
    carreras = models.CharField(max_length=40, default="SIS,CIV,IND,GES,CON",
                                help_text="Claves separadas por coma")
    profesor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="conferencias_asignadas")
    clave = models.CharField(max_length=32, default=secrets.token_hex, editable=False)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-hora_inicio"]

    def __str__(self):
        return f"{self.nombre} ({self.fecha:%d/%m/%Y})"

    def clean(self):
        if self.hora_inicio and self.hora_fin and self.hora_fin <= self.hora_inicio:
            raise ValidationError("La hora de fin debe ser posterior a la de inicio.")
        if self.creditos and self.creditos > 2:
            raise ValidationError("Una actividad no puede otorgar más de 2 créditos (RN-03).")

    @property
    def carreras_lista(self):
        return [c for c in self.carreras.split(",") if c]

    @property
    def carreras_nombres(self):
        return ", ".join(CARRERAS_DICT.get(c, c) for c in self.carreras_lista)

    def inicio_dt(self):
        return timezone.make_aware(datetime.combine(self.fecha, self.hora_inicio))

    def fin_dt(self):
        return timezone.make_aware(datetime.combine(self.fecha, self.hora_fin))

    def cierre_dt(self, cfg=None):
        """Fin de la ventana de registro: fin + tolerancia (RN-11)."""
        cfg = cfg or Configuracion.actual()
        return self.fin_dt() + timedelta(minutes=cfg.tolerancia_min)

    def estado(self):
        ahora = timezone.now()
        if ahora < self.inicio_dt():
            return "Programada"
        if ahora <= self.cierre_dt():
            return "Activa"
        return "Cerrada"


class Pregunta(models.Model):
    conferencia = models.ForeignKey(Conferencia, on_delete=models.CASCADE, related_name="preguntas")
    orden = models.PositiveSmallIntegerField(default=1)
    texto = models.CharField(max_length=300)
    opciones = models.JSONField(help_text="Lista de opciones")
    correcta = models.PositiveSmallIntegerField(help_text="Índice (desde 0) de la opción correcta")

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return self.texto


class Lote(models.Model):
    """Envío del Comité a Servicios Escolares (FR-10, FR-12)."""

    ENVIADO, CARGADO, FALLA = "enviado", "cargado", "falla"
    ESTADOS = [(ENVIADO, "Enviado a Servicios Escolares"), (CARGADO, "Cargado en el SIIC"),
               (FALLA, "Falla en la carga")]

    codigo = models.CharField(max_length=30, unique=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                    related_name="+")
    enviado = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ENVIADO)
    motivo_falla = models.TextField(blank=True)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="+")
    confirmado = models.DateTimeField(null=True, blank=True)
    exportaciones = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-enviado"]

    def __str__(self):
        return f"Lote {self.codigo}"


class Registro(models.Model):
    CELULAR, RED_LOCAL, ASISTIDO = "celular", "red_local", "asistido"
    ORIGENES = [(CELULAR, "Celular (QR)"), (RED_LOCAL, "Red local del profesor"),
                (ASISTIDO, "Asistido por profesor")]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True,
                            help_text="Lo genera el celular; evita duplicar al reenviar (FR-23)")
    folio = models.CharField(max_length=20, unique=True, null=True, blank=True)
    alumno = models.ForeignKey(Alumno, on_delete=models.PROTECT, related_name="registros")
    conferencia = models.ForeignKey(Conferencia, on_delete=models.PROTECT, related_name="registros")
    token = models.CharField(max_length=80, blank=True)
    minuto_qr = models.DateTimeField(null=True, blank=True, help_text="Hora que lleva el QR (RN-11)")
    respuestas = models.JSONField(default=list, blank=True)
    aciertos = models.PositiveSmallIntegerField(default=0)
    total = models.PositiveSmallIntegerField(default=0)
    porcentaje = models.FloatField(default=0)
    tiempo_seg = models.PositiveIntegerField(default=0)
    capturado_en = models.DateTimeField(null=True, blank=True, help_text="Hora del celular (informativa)")
    origen = models.CharField(max_length=10, choices=ORIGENES, default=CELULAR)
    motivo_asistido = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="+")
    valido = models.BooleanField(default=False)
    motivo = models.CharField(max_length=120, blank=True)
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.SET_NULL, related_name="registros")
    sincronizado_central = models.BooleanField(default=False, help_text="Solo en modo local (FR-24)")
    recibido = models.DateTimeField(auto_now_add=True)
    sello = models.CharField(max_length=64, blank=True, editable=False,
                             help_text="HMAC de los campos: delata cambios hechos fuera de la app")

    class Meta:
        ordering = ["-recibido"]
        constraints = [
            models.UniqueConstraint(fields=["alumno", "conferencia"], name="un_registro_por_conferencia"),
        ]

    def __str__(self):
        return f"{self.folio} · {self.alumno_id} · {self.conferencia}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.folio:
            self.folio = f"RT-{timezone.localdate():%y}-{self.pk:05d}"
            super().save(update_fields=["folio"])
        # Sello de integridad, calculado con los valores tal como quedaron en la base
        from .integridad import sello_registro
        guardado = Registro.objects.get(pk=self.pk)
        self.sello = sello_registro(guardado)
        Registro.objects.filter(pk=self.pk).update(sello=self.sello)

    def estado_alumno(self):
        """Estado que ve el alumno (A5). Nunca menciona el mínimo de conferencias (RN-13)."""
        if not self.valido:
            return "No válido"
        if self.lote is None:
            return "Validado por el sistema"
        return {Lote.ENVIADO: "Enviado a Servicios Escolares",
                Lote.CARGADO: "Cargado en el SIIC",
                Lote.FALLA: "Falla en la carga del SIIC"}[self.lote.estado]

    def paso(self):
        """0 a 3, para la barra de progreso de «Mi estado»."""
        if not self.valido:
            return 1
        if self.lote is None:
            return 1
        return 3 if self.lote.estado == Lote.CARGADO else 2


class Aviso(models.Model):
    CORREO, WHATSAPP = "correo", "whatsapp"
    PENDIENTE, ENVIADO, ERROR, SIMULADO = "pendiente", "enviado", "error", "simulado"
    ESTADOS = [(PENDIENTE, "Pendiente"), (ENVIADO, "Enviado"), (ERROR, "Error"),
               (SIMULADO, "Simulado (fuera de la lista blanca)")]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="avisos")
    canal = models.CharField(max_length=10, choices=[(CORREO, "Correo"), (WHATSAPP, "WhatsApp")])
    tipo = models.CharField(max_length=20)
    destino = models.CharField(max_length=120)
    asunto = models.CharField(max_length=160)
    contenido = models.TextField()
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    error = models.TextField(blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)
    enviado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado"]


class Bitacora(models.Model):
    """FR-18: quién hizo qué y cuándo."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=60)
    objeto = models.CharField(max_length=120)
    detalle = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    huella_anterior = models.CharField(max_length=64, blank=True, editable=False)
    huella = models.CharField(max_length=64, blank=True, editable=False,
                              help_text="Cadena de huellas: borrar o cambiar una entrada rompe la cadena")

    class Meta:
        ordering = ["-fecha"]
        verbose_name_plural = "Bitácora"

    @classmethod
    def registrar(cls, usuario, accion, objeto, detalle=""):
        if usuario is not None and not getattr(usuario, "is_authenticated", False):
            usuario = None
        from django.db import transaction

        from .integridad import huella_bitacora
        with transaction.atomic():
            ultima = cls.objects.order_by("-pk").values_list("huella", flat=True).first() or ""
            b = cls.objects.create(usuario=usuario, accion=accion[:60], objeto=str(objeto)[:120], detalle=detalle,
                                   huella_anterior=ultima)
            b = cls.objects.get(pk=b.pk)
            b.huella = huella_bitacora(b, ultima)
            cls.objects.filter(pk=b.pk).update(huella=b.huella)
        return b


class CodigoConsulta(models.Model):
    """FR-16: código de 6 dígitos enviado al correo institucional."""

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    codigo = models.CharField(max_length=6)
    expira = models.DateTimeField()
    usado = models.BooleanField(default=False)
    intentos = models.PositiveSmallIntegerField(default=0)

    @classmethod
    def nuevo(cls, alumno):
        cls.objects.filter(alumno=alumno, usado=False).update(usado=True)
        return cls.objects.create(alumno=alumno, codigo=f"{secrets.randbelow(10**6):06d}",
                                  expira=timezone.now() + timedelta(minutes=10))
