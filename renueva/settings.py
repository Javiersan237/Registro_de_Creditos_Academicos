"""
Configuración del prototipo funcional de Renueva TI (E4).

Todos los valores sensibles (contraseñas, tokens, números de prueba) se leen
del archivo .env, que NO se sube a Git. Ver .env.example.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Versión del salón: la app instalada es de solo lectura (Archivos de programa); el .env, la base de datos y los
# correos de prueba van en la carpeta de datos que indica el lanzador (RENUEVA_DATOS). Sin ella, todo en BASE_DIR.
DATOS_DIR = Path(os.environ["RENUEVA_DATOS"]) if os.environ.get("RENUEVA_DATOS") else BASE_DIR
load_dotenv(DATOS_DIR / ".env")


def env(clave, defecto=""):
    return os.environ.get(clave, defecto)


def env_lista(clave):
    return [x.strip() for x in env(clave).split(",") if x.strip()]


CLAVE_DE_EJEMPLO = "dev-inseguro-solo-para-pruebas-locales"
SECRET_KEY = env("DJANGO_SECRET_KEY", CLAVE_DE_EJEMPLO)
# Sin la variable, modo de producción: la depuración se enciende a propósito (DJANGO_DEBUG=1), nunca por olvido.
DEBUG = env("DJANGO_DEBUG", "0") == "1"
# En producción no hay comodín por defecto: sin DJANGO_ALLOWED_HOSTS, Django rechaza todas las peticiones (400).
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS") or (["*"] if DEBUG else [])
# Seguridad (versión del salón): fuera del modo de desarrollo no se arranca con claves de ejemplo.
if not DEBUG:
    from django.core.exceptions import ImproperlyConfigured
    # Obligatorias: la llave de Django y, con WhatsApp encendido, su token. QR_SIGNING_KEY y NIP_KEY vacías usan
    # DJANGO_SECRET_KEY; lo que nunca se permite son las claves de ejemplo.
    _obligatorias = {"DJANGO_SECRET_KEY"} | ({"WHATSAPP_TOKEN"} if env("WHATSAPP_ENABLED") == "1" else set())
    for _nombre in ("DJANGO_SECRET_KEY", "QR_SIGNING_KEY", "NIP_KEY", "WHATSAPP_TOKEN"):
        _valor = env(_nombre)
        if (not _valor and _nombre in _obligatorias) or _valor.startswith("cambia-") \
                or _valor == CLAVE_DE_EJEMPLO:
            raise ImproperlyConfigured(f"{_nombre} no está configurada en .env. Genera claves nuevas "
                                       "(el lanzador lo hace solo) antes de usar la app fuera de desarrollo.")
CSRF_TRUSTED_ORIGINS = env_lista("CSRF_TRUSTED_ORIGINS")
# Necesario cuando se expone con un túnel HTTPS (cloudflared) o en PythonAnywhere.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "registro",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sirve /static/ también con DEBUG=0 (laptop del salón con waitress) sin un servidor web aparte
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "renueva.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "registro.context.roles",
            ],
        },
    },
]

WSGI_APPLICATION = "renueva.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATOS_DIR / env("DB_NAME", "db.sqlite3"),
        # Registros simultáneos (NFR-05): espera hasta 20 s si otro hilo escribe, modo WAL
        # (lecturas sin bloquear escrituras) y transacciones IMMEDIATE (evita «database is locked»).
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}
# Versión del salón: con DB_CLAVE (64 hex, viene de la bóveda del lanzador) la base completa va cifrada con SQLCipher.
if env("DB_CLAVE"):
    DATABASES["default"]["ENGINE"] = "renueva.db_cifrada"
    DATABASES["default"]["CLAVE"] = env("DB_CLAVE")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True   # sirve static/ directo, sin collectstatic (la app instalada no puede escribir)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Seguridad (versión del salón, 24 nov 2026)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8          # la sesión del personal dura una jornada
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Con HTTPS (túnel o PythonAnywhere) las cookies solo viajan cifradas
HTTPS = env("HTTPS", "0") == "1"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = HTTPS
# Límites de intentos por IP (registro/seguridad.py)
LIMITES_ACTIVOS = env("LIMITES_ACTIVOS", "1") == "1"
LOGIN_MAX_INTENTOS = int(env("LOGIN_MAX_INTENTOS", "5"))
LOGIN_BLOQUEO_MIN = int(env("LOGIN_BLOQUEO_MIN", "15"))
CONFIAR_X_FORWARDED_FOR = env("CONFIAR_X_FORWARDED_FOR", "0") == "1"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/inicio/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Correo (FR-13, FR-15, FR-16, FR-27)
# Sin credenciales, los correos se guardan como archivos en la carpeta outbox/
# para poder revisarlos sin enviar nada.
# ---------------------------------------------------------------------------
if env("EMAIL_HOST_USER"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_TIMEOUT = 20
else:
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = DATOS_DIR / "outbox"
DEFAULT_FROM_EMAIL = env("EMAIL_FROM", "Renueva TI <avisos@renueva.local>")

# ---------------------------------------------------------------------------
# WhatsApp (FR-14, FR-27): servicio Node con whatsapp-web.js en whatsapp_service/
# ---------------------------------------------------------------------------
WHATSAPP_ENABLED = env("WHATSAPP_ENABLED", "0") == "1"
WHATSAPP_SERVICE_URL = env("WHATSAPP_SERVICE_URL", "http://127.0.0.1:3001")
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN")

# ---------------------------------------------------------------------------
# Seguridad en pruebas: en modo "prueba" solo se envían avisos reales a los
# correos y teléfonos de la lista blanca; al resto se les registra el aviso
# como "simulado" y no sale nada. Evita escribir a personas reales por error.
# ---------------------------------------------------------------------------
NOTIF_MODO = env("NOTIF_MODO", "prueba")  # prueba | real
NOTIF_LISTA_BLANCA_CORREOS = [c.lower() for c in env_lista("NOTIF_LISTA_BLANCA_CORREOS")]
NOTIF_LISTA_BLANCA_TELEFONOS = env_lista("NOTIF_LISTA_BLANCA_TELEFONOS")
NOTIF_ASYNC = env("NOTIF_ASYNC", "1") == "1"
# Versión del salón (24 nov 2026): solo WhatsApp. Canales activos, separados por coma (correo, whatsapp).
NOTIF_CANALES = env_lista("NOTIF_CANALES") or ["correo", "whatsapp"]
# El alumno escribe al registrarse el teléfono al que quiere su aviso (en el sistema real vendría del padrón).
# Con 1, ese número recibe avisos aunque no esté en la lista blanca: el alumno lo escribió y su NIP se verificó.
NOTIF_TELEFONO_ALUMNO = env("NOTIF_TELEFONO_ALUMNO", "1") == "1"
# Aviso por WhatsApp en cuanto el registro se recibe y es válido.
NOTIF_AVISO_RECIBIDO = env("NOTIF_AVISO_RECIBIDO", "1") == "1"
# Pausa mínima entre dos mensajes de WhatsApp, para que el número que envía no parezca spam.
WHATSAPP_PAUSA_SEG = float(env("WHATSAPP_PAUSA_SEG", "4"))

# ---------------------------------------------------------------------------
# QR firmado (FR-02, RN-11, NFR-07). La clave nunca va en el QR ni al celular.
# ---------------------------------------------------------------------------
QR_SIGNING_KEY = env("QR_SIGNING_KEY", SECRET_KEY)
# Clave con la que se guarda el NIP de los alumnos (HMAC). Si cambia, hay que volver a cargar el padrón.
NIP_KEY = env("NIP_KEY", SECRET_KEY)
# Clave de los sellos de integridad de registros y bitácora (registro/integridad.py)
INTEGRIDAD_KEY = env("INTEGRIDAD_KEY", SECRET_KEY)

# Archivo para el SIIC. CSV es decisión del consultor porque se convierte fácil a otros formatos; el formato es
# un cambio que puede realizarse a decisión de la empresa. El separador y la codificación se cambian aquí;
# otro tipo de archivo se agrega en registro/servicios.py (generar_csv) sin tocar el resto del sistema.
EXPORT_SEPARADOR = env("EXPORT_SEPARADOR", ",")
EXPORT_CODIFICACION = env("EXPORT_CODIFICACION", "utf-8")

NIP_MAX_INTENTOS = int(env("NIP_MAX_INTENTOS", "5"))
NIP_BLOQUEO_MIN = int(env("NIP_BLOQUEO_MIN", "15"))

# ---------------------------------------------------------------------------
# Modo B (FR-24): la laptop del profesor corre esta misma app sin internet y,
# al terminar, sube los registros al servidor central.
# ---------------------------------------------------------------------------
MODO_LOCAL = env("MODO_LOCAL", "0") == "1"
URL_PUBLICA = env("URL_PUBLICA", "")   # p. ej. http://192.168.1.50:8000 (la pone el lanzador del salón)
CENTRAL_URL = env("CENTRAL_URL", "")

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    # django.request: con DEBUG=0 los errores 500 quedan con su detalle en el registro (servidor.log en la laptop)
    "loggers": {"registro": {"handlers": ["console"], "level": "INFO"},
                "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
