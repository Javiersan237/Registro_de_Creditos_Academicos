"""Registro de créditos · Servidor del salón (TecNM Matehuala). Versión del salón, 24 nov 2026.

Una ventana con botones para encender el servidor y el WhatsApp en una laptop, sin .bat ni consolas.
El mismo ejecutable tiene varios modos (los usa la ventana, sin consola):

  RegistroCreditos.exe                       → la ventana (este archivo)
  RegistroCreditos.exe --servidor            → Django con waitress en 0.0.0.0:PUERTO
  RegistroCreditos.exe --preparar            → migraciones + datos simulados + conferencia del salón
  RegistroCreditos.exe --verificar           → revisa el archivo cifrado de la base (PRAGMA cipher_integrity_check)
  RegistroCreditos.exe --password-personal   → aplica las contraseñas de profesor, comite, servicios y admin (CLAVE_*)
  RegistroCreditos.exe --evento ACCION [DET] → anota una acción del administrador en la bitácora
  RegistroCreditos.exe --cifrar-base         → convierte una base sin cifrar (versión anterior) a SQLCipher

Seguridad (salon/boveda.py): la app pide una contraseña de administrador. Con ella y la cuenta de Windows (DPAPI)
se abre la bóveda que cifra la sesión de WhatsApp, las claves del sistema y la contraseña del personal.
Las claves nunca se escriben en .env: pasan a los procesos hijos por variables de entorno.

En desarrollo:  .venv\\Scripts\\python salon\\lanzador.py
Datos: %LOCALAPPDATA%\\RegistroCreditosTecNM (solo accesible para la cuenta de Windows que instaló)
"""
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

CONGELADO = getattr(sys, "frozen", False)
APP = Path(sys._MEIPASS) if CONGELADO else Path(__file__).resolve().parent.parent
if not CONGELADO:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
# resolve(): ruta larga (Chrome falla con rutas cortas tipo JAVIER~1)
DATOS = Path(os.environ.get("LOCALAPPDATA", Path.home())).resolve() / "RegistroCreditosTecNM"
LOGS = DATOS / "logs"
ENV = DATOS / ".env"
SESION = DATOS / "whatsapp_sesion"
INTENTOS = DATOS / "intentos.json"
SIN_VENTANA = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
AZUL, AZUL2, GRIS, VERDE, ROJO, AMARILLO = "#1B396A", "#2E5C9A", "#5A6475", "#1E7B4F", "#B4442F", "#B98900"
USUARIOS = ("profesor", "comite", "servicios", "admin")
CLAVES_USUARIOS = tuple(f"CLAVE_{u.upper()}" for u in USUARIOS)   # una contraseña distinta por usuario
SECRETOS = ("DJANGO_SECRET_KEY", "QR_SIGNING_KEY", "NIP_KEY", "INTEGRIDAD_KEY", "WHATSAPP_TOKEN", "SALON_PASSWORD",
            "DB_CLAVE", *CLAVES_USUARIOS)
MAX_INTENTOS, BLOQUEO_SEG = 5, 300


# ======================================================================= configuración
def leer_env():
    datos = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip()
    return datos


def crear_env_si_falta():
    """Configuración SIN secretos (los secretos van cifrados en la bóveda)."""
    DATOS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    if ENV.exists():
        return False
    ENV.write_text(f"""# Registro de créditos · laptop del salón. Configuración sin secretos: las claves van cifradas en la bóveda.
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=*
PUERTO=8000

# WhatsApp: se vincula con el celular que enviará los avisos
WHATSAPP_ENABLED=1
WHATSAPP_SERVICE_URL=http://127.0.0.1:3001
WHATSAPP_PORT=3001
WHATSAPP_LADA_PAIS=52
WHATSAPP_SESION_DIR={SESION}
WHATSAPP_PAUSA_SEG=4

# Avisos: solo WhatsApp, al número que escribe cada alumno
NOTIF_MODO=prueba
NOTIF_CANALES=whatsapp
NOTIF_TELEFONO_ALUMNO=1
NOTIF_AVISO_RECIBIDO=1
NOTIF_LISTA_BLANCA_TELEFONOS=
LIMITES_ACTIVOS=1
""", encoding="utf-8")
    return True


def quitar_secretos_del_env():
    """Migración: una instalación anterior guardaba las claves en .env. Se devuelven para meterlas en la bóveda."""
    if not ENV.exists():
        return {}
    viejos, lineas = {}, []
    for linea in ENV.read_text(encoding="utf-8").splitlines():
        k = linea.split("=", 1)[0].strip() if "=" in linea else ""
        if k in SECRETOS:
            viejos[k] = linea.split("=", 1)[1].strip()
        else:
            lineas.append(linea)
    if viejos:
        ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return viejos


def secretos_nuevos():
    clave = lambda: secrets.token_urlsafe(40)
    return {"DJANGO_SECRET_KEY": clave(), "QR_SIGNING_KEY": clave(), "NIP_KEY": clave(), "INTEGRIDAD_KEY": clave(),
            "WHATSAPP_TOKEN": secrets.token_hex(16), "DB_CLAVE": secrets.token_hex(32),   # DB_CLAVE: SQLCipher
            **claves_usuarios_nuevas()}


def contrasena_personal(usuario="profesor"):
    """Personal: «Tec-» + 11 caracteres. Admin (superusuario de /admin/): 32 caracteres, muy distinta."""
    if usuario == "admin":
        return secrets.token_urlsafe(24)
    return "Tec-" + secrets.token_urlsafe(8).replace("-", "x").replace("_", "y")


def claves_usuarios_nuevas():
    return {f"CLAVE_{u.upper()}": contrasena_personal(u) for u in USUARIOS}


def ip_local():
    """La dirección de la laptop en la red del salón (sin salir a internet)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no envía nada: solo elige la interfaz
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


# Puertos en uso en esta sesión. Si el de .env está ocupado por otro programa de la laptop, se usa el siguiente
# libre (8000 → 8001 → …; 3001 → 3002 → …) y la dirección y el QR se actualizan solos.
ACTIVOS = {}


def puerto():
    if "srv" in ACTIVOS:
        return ACTIVOS["srv"]
    return int(os.environ.get("PUERTO") or leer_env().get("PUERTO", "8000"))


def puerto_wa():
    if "wa" in ACTIVOS:
        return str(ACTIVOS["wa"])
    return os.environ.get("WHATSAPP_PORT") or leer_env().get("WHATSAPP_PORT", "3001")


def puerto_libre(desde, host="0.0.0.0", intentos=20):
    for p in range(desde, desde + intentos):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return None


def comando_propio(*args):
    if CONGELADO:
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def nodo():
    propio = APP / "node" / "node.exe"
    if propio.exists():
        return str(propio)
    for p in (r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe"):
        if Path(p).exists():
            return p
    return "node"


def http_get(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def http_post(url, datos, token, timeout=5):
    req = urllib.request.Request(url, data=json.dumps(datos).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-token": token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def matar(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=SIN_VENTANA)


def pid_archivo(nombre):
    return DATOS / f"{nombre}.pid"


# ======================================================================= modos sin ventana
def _a_log(nombre):
    LOGS.mkdir(parents=True, exist_ok=True)
    f = open(LOGS / f"{nombre}.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f
    print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
    return f


def _django():
    os.environ.update(RENUEVA_DATOS=str(DATOS), DJANGO_SETTINGS_MODULE="renueva.settings")
    if not CONGELADO:
        sys.path.insert(0, str(APP))
    import django
    django.setup()


def asegurar_base(con_datos=True):
    """Nunca se trabaja con una base vacía: crea o actualiza las tablas y, si no hay usuarios, carga la demostración."""
    from django.contrib.auth.models import User
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    if con_datos and not User.objects.exists():
        print("Base sin datos: se prepara la demostración del salón")
        call_command("preparar_salon")   # contraseñas: CLAVE_* del entorno (vienen de la bóveda)


def modo_servidor():
    _a_log("servidor")
    import warnings
    warnings.filterwarnings("ignore", message="No directory at")   # whitenoise: staticfiles/ no hace falta
    _django()
    asegurar_base()
    from waitress import serve
    from renueva.wsgi import application
    p = puerto()
    print(f"Servidor en http://0.0.0.0:{p}  (URL pública: {os.environ.get('URL_PUBLICA', '')})")
    serve(application, host="0.0.0.0", port=p, threads=16, ident="TecNM", channel_timeout=60)


def modo_preparar():
    _a_log("preparar")
    _django()
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=1)
    from django.contrib.auth.models import User
    # Con usuarios ya creados solo se reemplaza la conferencia del día: NO se regeneran los datos simulados
    # (eso borraba los teléfonos que escribieron los alumnos y el historial de avisos).
    call_command("preparar_salon", *(["--sin-datos"] if User.objects.exists() else []))
    print("PREPARADO_OK")


def modo_verificar():
    _a_log("verificar")
    _django()
    asegurar_base(con_datos=False)
    from registro.integridad import verificar
    from registro.models import Bitacora
    r = verificar()
    Bitacora.registrar(None, "Verificación de integridad", "Laptop del salón",
                       "Sin alteraciones" if r["ok"] else f"{len(r['problemas'])} problema(s)")
    (DATOS / "integridad.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False))


def modo_password_personal():
    _a_log("preparar")
    _django()
    from django.contrib.auth.models import User
    for u in User.objects.filter(username__in=USUARIOS):
        u.set_password(os.environ[f"CLAVE_{u.username.upper()}"])
        u.save()
    print("PASSWORD_OK")


def base_sin_cifrar(ruta):
    try:
        with open(ruta, "rb") as f:
            return f.read(16) == b"SQLite format 3" + bytes(1)
    except OSError:
        return False


def modo_cifrar_base():
    """Una instalación anterior dejó db.sqlite3 sin cifrar: se copia completa a una base SQLCipher y se borra la vieja."""
    _a_log("preparar")
    from sqlcipher3 import dbapi2 as sc
    ruta, nueva = DATOS / "db.sqlite3", DATOS / "db_cifrada.tmp"
    clave = os.environ["DB_CLAVE"]
    nueva.unlink(missing_ok=True)
    c = sc.connect(str(ruta))
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c.execute(f"ATTACH DATABASE '{nueva}' AS cifrada KEY \"x'{clave}'\"")
    c.execute("SELECT sqlcipher_export('cifrada')")
    c.execute("DETACH DATABASE cifrada")
    c.close()
    for f in ("db.sqlite3-wal", "db.sqlite3-shm"):
        (DATOS / f).unlink(missing_ok=True)
    with open(ruta, "r+b") as f:   # se sobreescribe la copia sin cifrar antes de borrarla
        f.write(os.urandom(ruta.stat().st_size))
    os.replace(nueva, ruta)
    print("BASE_CIFRADA_OK")


def modo_evento(accion, detalle):
    _a_log("eventos")
    _django()
    asegurar_base(con_datos=False)
    from registro.models import Bitacora
    Bitacora.registrar(None, accion, "Laptop del salón", detalle)


# ======================================================================= ventana
def ventana():
    import tkinter as tk
    from tkinter import messagebox, simpledialog

    import qrcode

    from boveda import Boveda, ContrasenaIncorrecta, carpeta_accesible, proteger_carpeta, reparar_carpeta

    # La versión 1.1 podía dejar archivos de la carpeta de datos sin permisos: se reparan antes de todo
    if DATOS.exists() and not carpeta_accesible(DATOS):
        reparar_carpeta(DATOS)
    nuevo_env = crear_env_si_falta()
    bov = Boveda(DATOS)
    sec = {}             # secretos en memoria (solo mientras la app está abierta y desbloqueada)
    procesos = {}

    try:   # letras nítidas en pantallas con escala de Windows
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    raiz = tk.Tk()

    def error_en_ventana(tipo, valor, tb):
        """Cualquier error de un botón se guarda en logs/ventana.log y se muestra (antes se perdía en silencio)."""
        import traceback
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            LOGS.mkdir(parents=True, exist_ok=True)
            with open(LOGS / "ventana.log", "a", encoding="utf-8") as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{texto}")
        except OSError:
            pass
        messagebox.showerror("Ocurrió un error", f"{tipo.__name__}: {valor}\n\nSe guardó el detalle en "
                                                 "«Ver registros» → ventana.log. Mándaselo a soporte.")
    raiz.report_callback_exception = error_en_ventana
    raiz.title("Registro de créditos · Servidor del salón · TecNM Matehuala")
    raiz.configure(bg="#F3F6FA")
    raiz.geometry("1100x860")
    raiz.minsize(1040, 800)
    try:
        raiz.iconbitmap(str(APP / "salon" / "icono.ico"))
    except tk.TclError:
        pass

    F = ("Segoe UI", 10)
    FB = ("Segoe UI Semibold", 11)

    def boton(padre, texto, cmd, primario=True, peligro=False):
        fondo = ROJO if peligro else (AZUL if primario else "#E3ECF7")
        return tk.Button(padre, text=texto, command=cmd, font=("Segoe UI Semibold", 10), cursor="hand2", relief="flat",
                         padx=14, pady=7, bg=fondo, fg="white" if (primario or peligro) else AZUL,
                         activebackground=AZUL2, activeforeground="white", highlightthickness=0, bd=0)

    # ---------------- franja institucional (siempre visible)
    franja = tk.Frame(raiz, bg="white")
    franja.pack(fill="x")
    imgs = []
    for nombre, sub in (("tecnm.png", 6), ("itmatehuala.png", 7)):
        try:
            im = tk.PhotoImage(file=str(APP / "static" / "img" / nombre)).subsample(sub)
            imgs.append(im)
            tk.Label(franja, image=im, bg="white").pack(side="left", padx=(16, 4), pady=8)
        except tk.TclError:
            pass
    tx = tk.Frame(franja, bg="white")
    tx.pack(side="left", padx=10)
    tk.Label(tx, text="Instituto Tecnológico de Matehuala", font=("Segoe UI Semibold", 15), fg=AZUL, bg="white").pack(anchor="w")
    tk.Label(tx, text="Registro de créditos complementarios · Servidor del salón", font=F, fg=GRIS, bg="white").pack(anchor="w")
    tk.Frame(raiz, bg=AZUL, height=4).pack(fill="x")

    contenedor = tk.Frame(raiz, bg="#F3F6FA")
    contenedor.pack(fill="both", expand=True)

    # ---------------- utilidades de seguridad
    def intentos():
        try:
            return json.loads(INTENTOS.read_text())
        except Exception:
            return {"n": 0, "hasta": 0}

    def guardar_intentos(d):
        INTENTOS.write_text(json.dumps(d))

    def evento(accion, detalle=""):
        """Anota una acción del administrador en la bitácora encadenada (en segundo plano)."""
        if not (DATOS / "db.sqlite3").exists():
            return
        threading.Thread(target=lambda: subprocess.run(comando_propio("--evento", accion, detalle), env=entorno_hijo(),
                                                       cwd=str(DATOS), capture_output=True, creationflags=SIN_VENTANA),
                         daemon=True).start()

    def entorno_hijo(extra=None):
        e = dict(os.environ, RENUEVA_DATOS=str(DATOS), DJANGO_SETTINGS_MODULE="renueva.settings", PYTHONIOENCODING="utf-8")
        e.update(sec)   # claves descifradas: solo en memoria y en el entorno de los procesos hijos
        e.update(extra or {})
        return e

    def pedir_admin(motivo):
        """Confirma la contraseña del administrador antes de una acción delicada."""
        d = intentos()
        if d["hasta"] > time.time():
            messagebox.showwarning("Bloqueado", f"Demasiados intentos. Espera {int(d['hasta'] - time.time()) // 60 + 1} min.")
            return False
        c = simpledialog.askstring("Contraseña de administrador", f"{motivo}\n\nEscribe la contraseña de administrador:",
                                   show="•", parent=raiz)
        if c is None:
            return False
        try:
            Boveda(DATOS).abrir(c)
            guardar_intentos({"n": 0, "hasta": 0})
            return True
        except ContrasenaIncorrecta:
            d["n"] += 1
            if d["n"] >= MAX_INTENTOS:
                d = {"n": 0, "hasta": time.time() + BLOQUEO_SEG}
            guardar_intentos(d)
            messagebox.showerror("Contraseña incorrecta", "La contraseña no coincide.")
            return False

    # ======================================================= pantalla de acceso
    def pantalla_acceso():
        marco = tk.Frame(contenedor, bg="white", highlightbackground="#C7D0DC", highlightthickness=1)
        marco.place(relx=0.5, rely=0.42, anchor="center", width=520)
        primera = not bov.existe()
        tk.Label(marco, text="Crear administrador" if primera else "Iniciar sesión", font=("Segoe UI Semibold", 15),
                 fg=AZUL, bg="white").pack(anchor="w", padx=24, pady=(20, 4))
        ayuda = ("Es la primera vez en esta laptop. Crea la contraseña del administrador: protege la sesión de "
                 "WhatsApp y las claves del sistema (se cifran con ella y con tu cuenta de Windows). "
                 "Mínimo 8 caracteres, con letras y números. No se puede recuperar si la olvidas."
                 if primera else "Escribe la contraseña del administrador de esta laptop.")
        tk.Label(marco, text=ayuda, font=F, fg=GRIS, bg="white", wraplength=470, justify="left").pack(anchor="w", padx=24)
        tk.Label(marco, text="Contraseña", font=FB, fg=AZUL, bg="white").pack(anchor="w", padx=24, pady=(14, 2))
        e1 = tk.Entry(marco, show="•", font=("Segoe UI", 12), relief="solid", bd=1)
        e1.pack(fill="x", padx=24, ipady=5)
        e2 = None
        if primera:
            tk.Label(marco, text="Repítela", font=FB, fg=AZUL, bg="white").pack(anchor="w", padx=24, pady=(10, 2))
            e2 = tk.Entry(marco, show="•", font=("Segoe UI", 12), relief="solid", bd=1)
            e2.pack(fill="x", padx=24, ipady=5)
        err = tk.Label(marco, text="", font=F, fg=ROJO, bg="white", wraplength=470, justify="left")
        err.pack(anchor="w", padx=24, pady=(6, 0))
        fila = tk.Frame(marco, bg="white")
        fila.pack(fill="x", padx=24, pady=(10, 20))

        def entrar(_=None):
            c = e1.get()
            d = intentos()
            if d["hasta"] > time.time():
                err.config(text=f"Demasiados intentos. Espera {int(d['hasta'] - time.time()) // 60 + 1} minutos.")
                return
            try:
                if primera:
                    if c != e2.get():
                        err.config(text="Las contraseñas no coinciden.")
                        return
                    if not Boveda.contrasena_valida(c):
                        err.config(text="Mínimo 8 caracteres, con letras y números.")
                        return
                    bov.crear(c)
                    s = secretos_nuevos()
                    s.update(quitar_secretos_del_env())   # conserva las claves de una instalación anterior
                    bov.guardar_secretos(s)
                    if not proteger_carpeta(DATOS):   # nunca debe dejarnos sin acceso
                        reparar_carpeta(DATOS)
                else:
                    bov.abrir(c)
            except ContrasenaIncorrecta:
                d["n"] += 1
                if d["n"] >= MAX_INTENTOS:
                    d = {"n": 0, "hasta": time.time() + BLOQUEO_SEG}
                    err.config(text="Demasiados intentos. Bloqueado 5 minutos.")
                else:
                    err.config(text=f"Contraseña incorrecta ({MAX_INTENTOS - d['n']} intentos restantes).")
                guardar_intentos(d)
                e1.delete(0, "end")
                return
            guardar_intentos({"n": 0, "hasta": 0})
            sec.clear()
            sec.update(bov.leer_secretos())
            viejos = quitar_secretos_del_env()   # por si quedó alguna clave en texto
            if viejos:
                sec.update({k: v for k, v in viejos.items() if k not in sec})
                bov.guardar_secretos(sec)
            sec.setdefault("INTEGRIDAD_KEY", sec.get("DJANGO_SECRET_KEY", secrets.token_urlsafe(40)))
            if "DB_CLAVE" not in sec:   # bóveda de una versión anterior: se agrega la llave de la base
                sec["DB_CLAVE"] = secrets.token_hex(32)
                bov.guardar_secretos(sec)
            claves_viejas = any(k not in sec for k in CLAVES_USUARIOS)
            if claves_viejas:   # versión anterior: una sola contraseña para todos → una distinta por usuario
                sec.update({k: v for k, v in claves_usuarios_nuevas().items() if k not in sec})
                sec.pop("SALON_PASSWORD", None)
                bov.guardar_secretos(sec)
            if base_sin_cifrar(DATOS / "db.sqlite3"):   # base de la versión anterior → se cifra completa
                err.config(text="Cifrando la base de datos de la versión anterior…", fg=AMARILLO)
                raiz.update()
                r = subprocess.run(comando_propio("--cifrar-base"), env=entorno_hijo(), cwd=str(DATOS),
                                   capture_output=True, creationflags=SIN_VENTANA)
                if r.returncode != 0 or base_sin_cifrar(DATOS / "db.sqlite3"):
                    err.config(text="No se pudo cifrar la base anterior. Revisa logs/preparar.log.", fg=ROJO)
                    return
            # Recuperación: si la app se cerró de golpe, la sesión pudo quedar sin cifrar
            for nombre in ("whatsapp", "servidor"):   # procesos que quedaron de un cierre de golpe
                if pid_archivo(nombre).exists():
                    try:
                        matar(int(pid_archivo(nombre).read_text()))
                    except ValueError:
                        pass
                    pid_archivo(nombre).unlink(missing_ok=True)
            if SESION.exists():
                time.sleep(1)
                bov.cifrar_carpeta(SESION)
            if claves_viejas and (DATOS / "db.sqlite3").exists():   # aplica las contraseñas nuevas a la base
                subprocess.run(comando_propio("--password-personal"), env=entorno_hijo(), cwd=str(DATOS),
                               capture_output=True, creationflags=SIN_VENTANA)
            marco.destroy()
            if primera:
                messagebox.showinfo("Administrador creado",
                                    "Listo. Guarda bien tu contraseña: sin ella no se puede abrir la sesión de WhatsApp.\n\n"
                                    "Las contraseñas de profesor, comite, servicios y admin (una distinta para cada "
                                    "uno) se ven con el botón «Mostrar» y piden esta misma contraseña.")
            pantalla_principal(primera)
            evento("Administrador creado" if primera else "Inicio de sesión del administrador")

        def olvide():
            if not messagebox.askyesno("Olvidé la contraseña",
                                       "Sin la contraseña no se puede abrir nada de lo cifrado.\n\n"
                                       "Restablecer BORRA: la sesión de WhatsApp (hay que volver a vincular), las claves "
                                       "y la base de datos de esta laptop (los registros se pierden).\n\n¿Continuar?"):
                return
            if not messagebox.askyesno("Confirmar", "¿Seguro? Esto no se puede deshacer."):
                return
            for nombre in ("whatsapp", "servidor"):
                if pid_archivo(nombre).exists():
                    try:
                        matar(int(pid_archivo(nombre).read_text()))
                    except ValueError:
                        pass
                    pid_archivo(nombre).unlink(missing_ok=True)
            bov.restablecer()
            shutil.rmtree(SESION, ignore_errors=True)
            for f in ("db.sqlite3", "db.sqlite3-wal", "db.sqlite3-shm", "intentos.json"):
                (DATOS / f).unlink(missing_ok=True)
            marco.destroy()
            pantalla_acceso()

        boton(fila, "Crear y entrar" if primera else "Entrar", entrar).pack(side="left")
        if not primera:
            boton(fila, "Olvidé la contraseña", olvide, False).pack(side="right")
        e1.bind("<Return>", entrar)
        if e2:
            e2.bind("<Return>", entrar)
        e1.focus_set()

    def puerto_ocupado(p):
        with socket.socket() as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", p)) == 0

    # ======================================================= pantalla principal
    def pantalla_principal(primera):
        # La barra de abajo se reserva primero: así nunca queda fuera de la ventana
        pie = tk.Frame(contenedor, bg="#F3F6FA")
        pie.pack(fill="x", padx=16, pady=(0, 12), side="bottom")
        cuerpo = tk.Frame(contenedor, bg="#F3F6FA")
        cuerpo.pack(fill="both", expand=True, padx=16, pady=12)
        izq = tk.Frame(cuerpo, bg="#F3F6FA")
        izq.pack(side="left", fill="both", expand=True)
        der = tk.Frame(cuerpo, bg="#F3F6FA")
        der.pack(side="right", fill="y", padx=(14, 0))

        def tarjeta(padre, titulo):
            t = tk.Frame(padre, bg="white", highlightbackground="#C7D0DC", highlightthickness=1)
            t.pack(fill="x", pady=(0, 10))
            tk.Label(t, text=titulo, font=FB, fg=AZUL, bg="white").pack(anchor="w", padx=14, pady=(10, 2))
            return t

        def estado_lbl(padre):
            fila = tk.Frame(padre, bg="white")
            fila.pack(fill="x", padx=14)
            punto = tk.Label(fila, text="●", font=("Segoe UI", 14), fg=GRIS, bg="white")
            punto.pack(side="left")
            txt = tk.Label(fila, text="Apagado", font=F, fg=GRIS, bg="white", wraplength=500, justify="left")
            txt.pack(side="left", padx=6)
            return punto, txt

        def pintar(punto, txt, color, texto):
            punto.config(fg=color)
            txt.config(text=texto)

        t1 = tarjeta(izq, "1 · Servidor")
        s_punto, s_txt = estado_lbl(t1)
        f1 = tk.Frame(t1, bg="white")
        f1.pack(anchor="w", padx=14, pady=(6, 12))

        t2 = tarjeta(izq, "2 · WhatsApp (avisos a los alumnos)")
        w_punto, w_txt = estado_lbl(t2)
        w_qr = tk.Label(t2, bg="white")
        w_qr.pack(padx=14)
        w_ayuda = tk.Label(t2, text="", font=F, fg=GRIS, bg="white", wraplength=520, justify="left")
        w_ayuda.pack(anchor="w", padx=14)
        f2 = tk.Frame(t2, bg="white")
        f2.pack(anchor="w", padx=14, pady=(6, 12))

        t3 = tarjeta(izq, "3 · Conferencia del salón")
        c_txt = tk.Label(t3, text="Prepara la conferencia de demostración «Renueva TI: así automatizamos tus créditos "
                                  "del Congreso», abierta hasta las 23:59 de hoy.", font=F, fg=GRIS, bg="white",
                         wraplength=520, justify="left")
        c_txt.pack(anchor="w", padx=14)
        f3 = tk.Frame(t3, bg="white")
        f3.pack(anchor="w", padx=14, pady=(6, 12))

        t4 = tarjeta(izq, "4 · Administración y seguridad")
        a_txt = tk.Label(t4, text="La base de datos, la sesión de WhatsApp y las claves están cifradas (AES-256 + "
                                  "Windows DPAPI + tu contraseña). Cada acción queda en la bitácora.", font=F, fg=GRIS,
                         bg="white", wraplength=520, justify="left")
        a_txt.pack(anchor="w", padx=14)
        f4 = tk.Frame(t4, bg="white")
        f4.pack(anchor="w", padx=14, pady=(6, 12))

        td = tk.Frame(der, bg="white", highlightbackground="#C7D0DC", highlightthickness=1)
        td.pack(fill="y")
        tk.Label(td, text="Para los celulares del salón", font=FB, fg=AZUL, bg="white").pack(padx=14, pady=(10, 2))
        tk.Label(td, text="Conéctense a la misma red Wi-Fi que esta laptop\ny escaneen este código:", font=F, fg=GRIS,
                 bg="white").pack(padx=14)
        lienzo = tk.Canvas(td, width=230, height=230, bg="white", highlightthickness=0)
        lienzo.pack(pady=6)
        url_lbl = tk.Label(td, text="", font=("Consolas", 11, "bold"), fg=AZUL, bg="white")
        url_lbl.pack()
        cred = tk.Label(td, text="", font=F, fg=GRIS, bg="white", justify="left")
        cred.pack(padx=14, pady=(8, 4), anchor="w")
        fd = tk.Frame(td, bg="white")
        fd.pack(padx=14, pady=(4, 12), fill="x")

        estado = {"ip": ip_local(), "srv": False, "qr_wa": None, "preparando": False, "url_qr": "",
                  "ocupado_wa": False, "ver_pwd": False}

        def url_base():
            return f"http://{estado['ip']}:{puerto()}"

        def dibujar_qr(url):
            if estado["url_qr"] == url:
                return
            estado["url_qr"] = url
            q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            q.add_data(url)
            q.make(fit=True)
            m = q.get_matrix()
            lado = 230 / len(m)
            lienzo.delete("all")
            for y, fila in enumerate(m):
                for x, v in enumerate(fila):
                    if v:
                        lienzo.create_rectangle(x * lado, y * lado, (x + 1) * lado, (y + 1) * lado, fill="black", width=0)

        def lanzar(nombre, args, extra_env=None):
            log = open(LOGS / f"{nombre}.log", "a", encoding="utf-8")
            p = subprocess.Popen(args, env=entorno_hijo(extra_env), cwd=str(DATOS), stdout=log,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=SIN_VENTANA)
            procesos[nombre] = p
            pid_archivo(nombre).write_text(str(p.pid))
            return p

        def detener(nombre):
            p = procesos.pop(nombre, None)
            pid = p.pid if p else None
            if pid is None and pid_archivo(nombre).exists():
                try:
                    pid = int(pid_archivo(nombre).read_text())
                except ValueError:
                    pid = None
            if pid:
                matar(pid)
            pid_archivo(nombre).unlink(missing_ok=True)

        def en_hilo(trabajo, al_final=None):
            def correr():
                r = trabajo()
                if al_final:
                    raiz.after(0, lambda: al_final(r))
            threading.Thread(target=correr, daemon=True).start()

        # ---- servidor
        def vivo(nombre):
            return nombre in procesos and procesos[nombre].poll() is None

        def elegir_wa():
            """Puerto del WhatsApp: se conserva si es nuestro o está libre; si otro programa lo tomó, el siguiente libre."""
            actual = ACTIVOS.get("wa")
            if actual and (vivo("whatsapp") or puerto_libre(actual, "127.0.0.1", 1)):
                return actual
            base = int(leer_env().get("WHATSAPP_PORT", "3001"))
            ACTIVOS["wa"] = puerto_libre(base, "127.0.0.1") or base
            return ACTIVOS["wa"]

        def encender_servidor():
            if vivo("servidor"):
                return
            if estado["preparando"]:   # primero termina la preparación de la base; luego enciende
                pintar(s_punto, s_txt, AMARILLO, "Esperando a que termine la preparación de la base…")
                raiz.after(1000, encender_servidor)
                return
            estado["ip"] = ip_local()
            detener("servidor")
            base = int(leer_env().get("PUERTO", "8000"))
            p = puerto_libre(base)
            if p is None:
                pintar(s_punto, s_txt, ROJO, f"No hay puertos libres entre {base} y {base + 19}. Cierra otros programas.")
                return
            ACTIVOS["srv"] = p
            wa = elegir_wa()
            lanzar("servidor", comando_propio("--servidor"),
                   {"URL_PUBLICA": url_base(), "PUERTO": str(p), "WHATSAPP_SERVICE_URL": f"http://127.0.0.1:{wa}"})
            nota = "" if p == base else f" (el {base} estaba ocupado: se usa el {p})"
            pintar(s_punto, s_txt, AMARILLO, "Encendiendo…" + nota)

        def apagar_servidor():
            detener("servidor")
            pintar(s_punto, s_txt, GRIS, "Apagado")

        # ---- WhatsApp (la sesión solo existe sin cifrar mientras el servicio está encendido)
        def encender_whatsapp():
            if estado["ocupado_wa"] or ("whatsapp" in procesos and procesos["whatsapp"].poll() is None):
                return
            estado["ocupado_wa"] = True
            pintar(w_punto, w_txt, AMARILLO, "Abriendo la sesión cifrada…")

            def trabajo():
                if not SESION.exists():
                    bov.descifrar_carpeta(SESION)
                return True

            def listo(_):
                estado["ocupado_wa"] = False
                detener("whatsapp")
                antes = ACTIVOS.get("wa")
                wa = elegir_wa()
                lanzar("whatsapp", [nodo(), str(APP / "whatsapp_service" / "index.js")],
                       {"WHATSAPP_SESION_DIR": str(SESION), "WHATSAPP_PORT": str(wa)})
                if antes and antes != wa and vivo("servidor"):   # el servidor debe conocer el puerto nuevo
                    apagar_servidor()
                    encender_servidor()
                pintar(w_punto, w_txt, AMARILLO, "Encendiendo WhatsApp… (la primera vez tarda hasta un minuto)")
            en_hilo(trabajo, listo)

        def _parar_whatsapp(ruta="/apagar"):
            try:   # cierre ordenado: guarda la sesión
                http_post(f"http://127.0.0.1:{puerto_wa()}{ruta}", {}, sec.get("WHATSAPP_TOKEN", ""))
                for _ in range(40):
                    p = procesos.get("whatsapp")
                    if not p or p.poll() is not None:
                        break
                    time.sleep(0.5)
            except Exception:
                pass
            detener("whatsapp")
            time.sleep(1)   # el navegador escondido suelta los archivos

        def apagar_whatsapp(al_final=None):
            if estado["ocupado_wa"]:
                return
            estado["ocupado_wa"] = True
            pintar(w_punto, w_txt, AMARILLO, "Apagando y cifrando la sesión…")

            def trabajo():
                _parar_whatsapp()
                return bov.cifrar_carpeta(SESION)

            def listo(_):
                estado["ocupado_wa"] = False
                w_qr.config(image="")
                estado["qr_wa"] = None
                w_ayuda.config(text="")
                pintar(w_punto, w_txt, GRIS, "Apagado · sesión cifrada")
                if al_final:
                    al_final()
            en_hilo(trabajo, listo)

        def cambiar_numero():
            if not pedir_admin("Cambiar el número de WhatsApp cierra la sesión actual: el dispositivo desaparecerá "
                               "del celular vinculado y habrá que escanear un QR nuevo."):
                return
            estado["ocupado_wa"] = True
            pintar(w_punto, w_txt, AMARILLO, "Cerrando la sesión del número actual…")

            def trabajo():
                if "whatsapp" in procesos and procesos["whatsapp"].poll() is None:
                    _parar_whatsapp("/cerrar_sesion")
                bov.borrar_sesion(SESION)
                return True

            def listo(_):
                estado["ocupado_wa"] = False
                evento("Cambio de número de WhatsApp", "Sesión anterior cerrada y borrada")
                encender_whatsapp()
            en_hilo(trabajo, listo)

        # ---- conferencia
        def preparar():
            if estado["preparando"]:
                return
            estado["preparando"] = True
            c_txt.config(text="Preparando datos y conferencia… (unos segundos)", fg=AMARILLO)

            def trabajo():
                r = subprocess.run(comando_propio("--preparar"), env=entorno_hijo(), cwd=str(DATOS),
                                   capture_output=True, creationflags=SIN_VENTANA)
                log = (LOGS / "preparar.log").read_text(encoding="utf-8", errors="replace") if (LOGS / "preparar.log").exists() else ""
                return r.returncode == 0 and "PREPARADO_OK" in log[-4000:]

            def fin(ok):
                estado["preparando"] = False
                if ok:
                    c_txt.config(text=f"✔ Conferencia lista ({time.strftime('%H:%M')}). Abre el panel del profesor para "
                                      "mostrar el QR de la conferencia.", fg=VERDE)
                    evento("Conferencia del salón preparada")
                else:
                    try:
                        ultimas = (LOGS / "preparar.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
                    except (OSError, IndexError):
                        ultimas = ""
                    c_txt.config(text=f"No se pudo preparar: {ultimas[:160]}\nRevisa «Ver registros» → preparar.log.",
                                 fg=ROJO)
            en_hilo(trabajo, fin)

        # ---- administración
        def mostrar_pwd():
            if estado["ver_pwd"]:
                estado["ver_pwd"] = False
            elif pedir_admin("Mostrar las contraseñas del personal."):
                estado["ver_pwd"] = True
                raiz.after(30000, lambda: (estado.update(ver_pwd=False), actualizar_cred()))   # se oculta sola
                actualizar_cred()
                messagebox.showinfo("Contraseñas del personal",
                                    "\n".join(f"{u}:  {sec.get(f'CLAVE_{u.upper()}', '—')}" for u in USUARIOS) +
                                    "\n\nTambién quedan visibles 30 segundos en la tarjeta de la derecha.")
            actualizar_cred()

        def cambiar_pwd_personal():
            if not pedir_admin("Cambiar la contraseña de un usuario del personal."):
                return
            usuario = (simpledialog.askstring("Contraseña del personal",
                                              "¿De qué usuario? (profesor, comite, servicios o admin)", parent=raiz)
                       or "").strip().lower()
            if usuario not in USUARIOS:
                if usuario:
                    messagebox.showerror("Usuario", "Escribe profesor, comite, servicios o admin.")
                return
            nueva = simpledialog.askstring("Contraseña del personal",
                                           f"Nueva contraseña de {usuario} (mínimo 8, con letras y números).\n"
                                           "Déjala vacía para generar una al azar:", show="•", parent=raiz)
            if nueva is None:
                return
            nueva = nueva or contrasena_personal(usuario)
            if not Boveda.contrasena_valida(nueva):
                messagebox.showerror("Contraseña débil", "Mínimo 8 caracteres, con letras y números.")
                return
            otros = {k: v for k, v in sec.items() if k in CLAVES_USUARIOS and k != f"CLAVE_{usuario.upper()}"}
            if nueva in otros.values():
                messagebox.showerror("Contraseña repetida", "Cada usuario debe tener una contraseña distinta.")
                return

            def trabajo():
                if not (DATOS / "db.sqlite3").exists():
                    return True
                r = subprocess.run(comando_propio("--password-personal"),
                                   env=entorno_hijo({f"CLAVE_{usuario.upper()}": nueva}), cwd=str(DATOS),
                                   capture_output=True, creationflags=SIN_VENTANA)
                return r.returncode == 0

            def fin(ok):
                if ok:
                    sec[f"CLAVE_{usuario.upper()}"] = nueva
                    bov.guardar_secretos(sec)
                    evento("Cambio de contraseña del personal", usuario)
                    messagebox.showinfo("Listo", f"Contraseña de {usuario} actualizada.")
                    actualizar_cred()
                else:
                    messagebox.showerror("Error", "No se pudo cambiar. Revisa «Ver registros».")
            en_hilo(trabajo, fin)

        def cambiar_pwd_admin():
            actual = simpledialog.askstring("Contraseña de administrador", "Contraseña actual:", show="•", parent=raiz)
            if actual is None:
                return
            nueva = simpledialog.askstring("Contraseña de administrador",
                                           "Contraseña nueva (mínimo 8, con letras y números):", show="•", parent=raiz)
            if nueva is None:
                return
            otra = simpledialog.askstring("Contraseña de administrador", "Repite la contraseña nueva:", show="•", parent=raiz)
            if nueva != otra:
                messagebox.showerror("No coinciden", "Las contraseñas nuevas no coinciden.")
                return
            try:
                bov.cambiar_contrasena(actual, nueva)
            except ContrasenaIncorrecta:
                messagebox.showerror("Contraseña incorrecta", "La contraseña actual no coincide.")
                return
            except ValueError as e:
                messagebox.showerror("Contraseña débil", str(e))
                return
            evento("Cambio de contraseña del administrador")
            messagebox.showinfo("Listo", "Contraseña de administrador cambiada.")

        def verificar():
            a_txt.config(text="Verificando el archivo cifrado de la base (cada página)…", fg=AMARILLO)

            def trabajo():
                (DATOS / "integridad.json").unlink(missing_ok=True)
                subprocess.run(comando_propio("--verificar"), env=entorno_hijo(), cwd=str(DATOS),
                               capture_output=True, creationflags=SIN_VENTANA)
                try:
                    return json.loads((DATOS / "integridad.json").read_text(encoding="utf-8"))
                except Exception:
                    return None

            def fin(r):
                if r is None:
                    a_txt.config(text="No se pudo verificar (¿ya preparaste la conferencia?).", fg=ROJO)
                elif r["ok"]:
                    a_txt.config(text=f"✔ Sin alteraciones en el archivo cifrado: {r['registros']} registros y "
                                      f"{r['bitacora']} entradas de bitácora ({time.strftime('%H:%M')}).", fg=VERDE)
                else:
                    a_txt.config(text="⚠ Se detectaron cambios hechos fuera de la app:\n• " +
                                      "\n• ".join(r["problemas"][:6]), fg=ROJO)
            en_hilo(trabajo, fin)

        # ---- todo
        def encender_todo():
            if not (DATOS / "db.sqlite3").exists():
                preparar()   # encender_servidor espera a que termine
            encender_servidor()
            encender_whatsapp()

        def apagar_todo(al_final=None):
            apagar_servidor()
            apagar_whatsapp(al_final)

        def ver_registros():
            os.startfile(str(LOGS))

        def acerca():
            if estado["srv"]:
                webbrowser.open(f"{url_base()}/acerca/")
            else:
                messagebox.showinfo("Acerca de", "Registro de créditos complementarios del Congreso Académico\n"
                                                 "Instituto Tecnológico de Matehuala · Tecnológico Nacional de México\n\n"
                                                 "Desarrollado por Renueva TI (consultora)\nRenovando Mundos, Renovándote a ti")

        boton(f1, "Encender servidor", encender_servidor).pack(side="left")
        boton(f1, "Apagar", apagar_servidor, False).pack(side="left", padx=8)
        boton(f2, "Encender y vincular", encender_whatsapp).pack(side="left")
        boton(f2, "Apagar", lambda: apagar_whatsapp(), False).pack(side="left", padx=8)
        boton(f2, "Cambiar número", cambiar_numero, False).pack(side="left")
        boton(f3, "Preparar conferencia de hoy", preparar).pack(side="left")
        boton(f4, "Verificar integridad", verificar).pack(side="left")
        boton(f4, "Contraseña del personal", cambiar_pwd_personal, False).pack(side="left", padx=8)
        boton(f4, "Contraseña de administrador", cambiar_pwd_admin, False).pack(side="left")
        boton(fd, "Abrir panel del profesor", lambda: webbrowser.open(f"{url_base()}/profesor/")).pack(fill="x")
        boton(fd, "Abrir página de inicio", lambda: webbrowser.open(f"{url_base()}/"), False).pack(fill="x", pady=(6, 0))
        boton(fd, "Mostrar / ocultar contraseña", mostrar_pwd, False).pack(fill="x", pady=(6, 0))

        boton(pie, "▶  Encender todo", encender_todo).pack(side="left")
        boton(pie, "■  Apagar todo", lambda: apagar_todo(), False).pack(side="left", padx=8)
        boton(pie, "Ver registros", ver_registros, False).pack(side="right")
        boton(pie, "Acerca de", acerca, False).pack(side="right", padx=8)

        def actualizar_cred():
            claves = "\n".join(f"{u}: {sec.get(f'CLAVE_{u.upper()}', '—') if estado['ver_pwd'] else '••••••••'}"
                                for u in USUARIOS)
            cred.config(text=f"Personal (una contraseña distinta para cada uno):\n{claves}\n\n"
                             "Alumnos de prueba: 99660002 a 99660051\nNIP: últimos 4 dígitos al revés\n"
                             "(99660002 → 2000)")

        # ---- sondeo de estado (en un hilo, para no congelar la ventana)
        def sondear():
            while True:
                srv, wa = False, None   # solo se consultan NUESTROS puertos (no otro servidor de la laptop)
                if "srv" in ACTIVOS:
                    try:
                        srv = http_get(f"http://127.0.0.1:{puerto()}/acerca/")[0] == 200
                    except Exception:
                        srv = False
                if "wa" in ACTIVOS and vivo("whatsapp"):
                    try:
                        wa = json.loads(http_get(f"http://127.0.0.1:{puerto_wa()}/qr.json")[1])
                    except Exception:
                        wa = None
                raiz.after(0, lambda s=srv, w=wa: pintar_estado(s, w))
                time.sleep(2)

        def pintar_estado(srv, wa):
            estado["srv"] = srv
            p = procesos.get("servidor")
            if srv:
                pintar(s_punto, s_txt, VERDE, f"Encendido en {url_base()}")
            elif p and p.poll() is None:
                pintar(s_punto, s_txt, AMARILLO, "Encendiendo…")
            elif p and p.poll() is not None:
                pintar(s_punto, s_txt, ROJO, "Se detuvo. Revisa «Ver registros» → servidor.log")
            dibujar_qr(f"{url_base()}/app/")
            url_lbl.config(text=f"{url_base()}/app/")
            if estado["ocupado_wa"]:
                return
            pw = procesos.get("whatsapp")
            if wa is None:
                if pw and pw.poll() is None:
                    pintar(w_punto, w_txt, AMARILLO, "Encendiendo WhatsApp…")
                elif pw:
                    pintar(w_punto, w_txt, ROJO, "Se detuvo. Revisa «Ver registros» → whatsapp.log")
                return
            if wa.get("listo"):
                pintar(w_punto, w_txt, VERDE, f"Conectado · número vinculado: {wa.get('numero') or '—'}")
                if estado["qr_wa"]:
                    w_qr.config(image="")
                    estado["qr_wa"] = None
                    w_ayuda.config(text="")
            elif wa.get("qr"):
                pintar(w_punto, w_txt, AMARILLO, "Escanea este código con el WhatsApp que enviará los avisos")
                if estado["qr_wa"] != wa["qr"]:
                    estado["qr_wa"] = wa["qr"]
                    foto = tk.PhotoImage(data=wa["qr"].split(",", 1)[1]).subsample(2)
                    w_qr.config(image=foto)
                    w_qr.image = foto
                    w_ayuda.config(text="En el celular: WhatsApp → ⋮ → Dispositivos vinculados → Vincular un "
                                        "dispositivo. Al apagar, la sesión se guarda cifrada en esta laptop.")
            else:
                pintar(w_punto, w_txt, AMARILLO, wa.get("detalle", "Cargando…"))

        def al_cerrar():
            if procesos or estado["srv"] or SESION.exists():
                if not messagebox.askyesno("Salir", "Se apagará el servidor y el WhatsApp, y la sesión se guardará "
                                                    "cifrada. ¿Salir?"):
                    return
                for b in (f1, f2, f3, f4, fd, pie):
                    for w in b.winfo_children():
                        w.config(state="disabled")
                apagar_todo(lambda: (sec.clear(), bov.cerrar(), raiz.destroy()))
            else:
                sec.clear()
                bov.cerrar()
                raiz.destroy()

        raiz.protocol("WM_DELETE_WINDOW", al_cerrar)
        actualizar_cred()
        dibujar_qr(f"{url_base()}/app/")
        url_lbl.config(text=f"{url_base()}/app/")
        threading.Thread(target=sondear, daemon=True).start()
        if primera:
            messagebox.showinfo("Primera vez", "1. Presiona «Encender todo».\n"
                                               "2. Escanea el código de WhatsApp con tu celular.\n"
                                               "3. Abre el panel del profesor y muestra el QR de la conferencia.\n\n"
                                               "Si Windows pregunta por el firewall, elige «Permitir».")

    raiz.protocol("WM_DELETE_WINDOW", raiz.destroy)
    pantalla_acceso()
    raiz.mainloop()


def una_sola_instancia():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 38117))
        return s
    except OSError:
        return None


if __name__ == "__main__":
    if "--servidor" in sys.argv:
        modo_servidor()
    elif "--preparar" in sys.argv:
        modo_preparar()
    elif "--verificar" in sys.argv:
        modo_verificar()
    elif "--password-personal" in sys.argv:
        modo_password_personal()
    elif "--cifrar-base" in sys.argv:
        modo_cifrar_base()
    elif "--evento" in sys.argv:
        i = sys.argv.index("--evento")
        modo_evento(sys.argv[i + 1] if len(sys.argv) > i + 1 else "Evento",
                    sys.argv[i + 2] if len(sys.argv) > i + 2 else "")
    else:
        candado = una_sola_instancia()
        if candado is None:
            import tkinter.messagebox as mb
            mb.showinfo("Registro de créditos", "La app ya está abierta.")
            sys.exit(0)
        ventana()
