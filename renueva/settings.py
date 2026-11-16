"""
Configuración del prototipo funcional de Renueva TI (E4).

Todos los valores sensibles (contraseñas, tokens, números de prueba) se leen
del archivo .env, que NO se sube a Git. Ver .env.example.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(clave, defecto=""):
    return os.environ.get(clave, defecto)


def env_lista(clave):
    return [x.strip() for x in env(clave).split(",") if x.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-inseguro-solo-para-pruebas-locales")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS") or ["*"]
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
        "NAME": BASE_DIR / env("DB_NAME", "db.sqlite3"),
        # Registros simultáneos (NFR-05): espera hasta 20 s si otro hilo escribe, modo WAL
        # (lecturas sin bloquear escrituras) y transacciones IMMEDIATE (evita «database is locked»).
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
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
    EMAIL_FILE_PATH = BASE_DIR / "outbox"
DEFAULT_FROM_EMAIL = env("EMAIL_FROM", "Renueva TI <avisos@renueva.local>")

# ---------------------------------------------------------------------------
# WhatsApp (FR-14, FR-27): servicio Node con whatsapp-web.js en whatsapp_service/
# ---------------------------------------------------------------------------
WHATSAPP_ENABLED = env("WHATSAPP_ENABLED", "0") == "1"
WHATSAPP_SERVICE_URL = env("WHATSAPP_SERVICE_URL", "http://127.0.0.1:3001")
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN", "cambia-este-token")

# ---------------------------------------------------------------------------
# Seguridad en pruebas: en modo "prueba" solo se envían avisos reales a los
# correos y teléfonos de la lista blanca; al resto se les registra el aviso
# como "simulado" y no sale nada. Evita escribir a personas reales por error.
# ---------------------------------------------------------------------------
NOTIF_MODO = env("NOTIF_MODO", "prueba")  # prueba | real
NOTIF_LISTA_BLANCA_CORREOS = [c.lower() for c in env_lista("NOTIF_LISTA_BLANCA_CORREOS")]
NOTIF_LISTA_BLANCA_TELEFONOS = env_lista("NOTIF_LISTA_BLANCA_TELEFONOS")
NOTIF_ASYNC = env("NOTIF_ASYNC", "1") == "1"

# ---------------------------------------------------------------------------
# QR firmado (FR-02, RN-11, NFR-07). La clave nunca va en el QR ni al celular.
# ---------------------------------------------------------------------------
QR_SIGNING_KEY = env("QR_SIGNING_KEY", SECRET_KEY)

# ---------------------------------------------------------------------------
# Modo B (FR-24): la laptop del profesor corre esta misma app sin internet y,
# al terminar, sube los registros al servidor central.
# ---------------------------------------------------------------------------
MODO_LOCAL = env("MODO_LOCAL", "0") == "1"
CENTRAL_URL = env("CENTRAL_URL", "")

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"registro": {"handlers": ["console"], "level": "INFO"}},
}
