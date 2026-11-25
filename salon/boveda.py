"""Bóveda de la laptop del salón (24 nov 2026): protege la sesión de WhatsApp, las claves y la contraseña del personal.

Dos llaves a la vez:
  1. DPAPI de Windows → atada a la cuenta de Windows y a esta computadora (copiar la carpeta a otro equipo no sirve).
  2. La contraseña del administrador de la app → se mezcla con DPAPI como «entropía» (PBKDF2-SHA256, 600 000 vueltas).

Con las dos se abre una LLAVE MAESTRA aleatoria (32 bytes) que cifra con AES-256-GCM:
  - secretos.bin           → claves del sistema y contraseña del personal (JSON)
  - whatsapp_sesion.bin    → la carpeta de la sesión de WhatsApp, comprimida
AES-GCM también detecta si alguien alteró el archivo cifrado (no se descifra).
"""
import base64
import ctypes
import ctypes.wintypes as wt
import io
import json
import os
import shutil
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VUELTAS = 600_000
# Carpetas de caché del navegador: se vuelven a crear solas y solo harían pesado el archivo cifrado
CACHES = {"Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache", "GrShaderCache",
          "ShaderCache", "GraphiteDawnCache", "Crashpad", "component_crx_cache", "BrowserMetrics"}


class ContrasenaIncorrecta(Exception):
    pass


# ----------------------------------------------------------------------------------------------- DPAPI (Windows)
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(datos):
    buf = ctypes.create_string_buffer(datos, len(datos))
    return _BLOB(len(datos), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(proteger, datos, entropia):
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    entrada, _b1 = _blob(datos)
    ent, _b2 = _blob(entropia)
    salida = _BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    f = crypt32.CryptProtectData if proteger else crypt32.CryptUnprotectData
    args = (ctypes.byref(entrada), "Registro de creditos TecNM" if proteger else None, ctypes.byref(ent),
            None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(salida))
    if not f(*args):
        raise ContrasenaIncorrecta("No se pudo abrir la bóveda (contraseña incorrecta o es otra cuenta de Windows).")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)


def _derivar(contrasena, sal):
    return PBKDF2HMAC(algorithm=SHA256(), length=32, salt=sal, iterations=VUELTAS).derive(contrasena.encode("utf-8"))


# ----------------------------------------------------------------------------------------------- bóveda
class Boveda:
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.archivo = self.carpeta / "boveda.json"
        self.secretos_bin = self.carpeta / "secretos.bin"
        self.sesion_bin = self.carpeta / "whatsapp_sesion.bin"
        self._llave = None

    # ---- alta y apertura
    def existe(self):
        return self.archivo.exists()

    @staticmethod
    def contrasena_valida(c):
        """Mínimo 8 caracteres, con letras y números."""
        return len(c) >= 8 and any(ch.isalpha() for ch in c) and any(ch.isdigit() for ch in c)

    def crear(self, contrasena):
        if not self.contrasena_valida(contrasena):
            raise ValueError("La contraseña debe tener al menos 8 caracteres, con letras y números.")
        self._llave = AESGCM.generate_key(bit_length=256)
        self._guardar_llave(contrasena)

    def _guardar_llave(self, contrasena):
        sal = os.urandom(16)
        envuelta = _dpapi(True, self._llave, _derivar(contrasena, sal))
        tmp = self.archivo.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "sal": base64.b64encode(sal).decode(),
                                   "llave": base64.b64encode(envuelta).decode()}), encoding="utf-8")
        os.replace(tmp, self.archivo)

    def abrir(self, contrasena):
        d = json.loads(self.archivo.read_text(encoding="utf-8"))
        llave = _dpapi(False, base64.b64decode(d["llave"]), _derivar(contrasena, base64.b64decode(d["sal"])))
        if len(llave) != 32:
            raise ContrasenaIncorrecta("La bóveda está dañada.")
        self._llave = llave

    def cambiar_contrasena(self, actual, nueva):
        self.abrir(actual)
        if not self.contrasena_valida(nueva):
            raise ValueError("La contraseña nueva debe tener al menos 8 caracteres, con letras y números.")
        self._guardar_llave(nueva)

    def cerrar(self):
        self._llave = None

    @property
    def abierta(self):
        return self._llave is not None

    # ---- cifrado
    def _cifrar(self, datos, etiqueta):
        nonce = os.urandom(12)
        return b"RTB1" + nonce + AESGCM(self._llave).encrypt(nonce, datos, etiqueta)

    def _descifrar(self, datos, etiqueta):
        if datos[:4] != b"RTB1":
            raise ValueError("Archivo cifrado desconocido.")
        return AESGCM(self._llave).decrypt(datos[4:16], datos[16:], etiqueta)   # falla si alguien lo alteró

    def _escribir(self, ruta, datos):
        tmp = ruta.with_suffix(".tmp")
        tmp.write_bytes(datos)
        os.replace(tmp, ruta)

    # ---- secretos
    def leer_secretos(self):
        if not self.secretos_bin.exists():
            return {}
        return json.loads(self._descifrar(self.secretos_bin.read_bytes(), b"secretos"))

    def guardar_secretos(self, secretos):
        self._escribir(self.secretos_bin, self._cifrar(json.dumps(secretos).encode(), b"secretos"))

    # ---- sesión de WhatsApp
    def cifrar_carpeta(self, carpeta):
        """Comprime y cifra la carpeta de la sesión; después la borra. Devuelve True si había algo que cifrar."""
        carpeta = Path(carpeta)
        if not carpeta.exists():
            return False
        buf = io.BytesIO()
        # strict_timestamps=False: Chrome deja archivos con fecha anterior a 1980, que ZIP no acepta (se ajusta a 1980)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6, strict_timestamps=False) as z:
            for raiz, dirs, archivos in os.walk(carpeta):
                dirs[:] = [d for d in dirs if d not in CACHES]
                for a in archivos:
                    p = Path(raiz) / a
                    if a in ("LOCK", "lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"):
                        continue
                    try:
                        z.write(p, p.relative_to(carpeta).as_posix())
                    except (PermissionError, OSError):
                        pass   # archivo en uso de un navegador que no cerró: se omite
        self._escribir(self.sesion_bin, self._cifrar(buf.getvalue(), b"whatsapp"))
        shutil.rmtree(carpeta, ignore_errors=True)
        return True

    def descifrar_carpeta(self, carpeta):
        """Restaura la sesión en la carpeta (solo mientras la app está encendida)."""
        if not self.sesion_bin.exists():
            return False
        datos = self._descifrar(self.sesion_bin.read_bytes(), b"whatsapp")
        carpeta = Path(carpeta)
        shutil.rmtree(carpeta, ignore_errors=True)
        carpeta.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            for nombre in z.namelist():   # sin rutas que se salgan de la carpeta
                destino = (carpeta / nombre).resolve()
                if carpeta.resolve() not in destino.parents and destino != carpeta.resolve():
                    raise ValueError("Archivo de sesión inválido.")
            z.extractall(carpeta)
        return True

    def borrar_sesion(self, carpeta):
        shutil.rmtree(carpeta, ignore_errors=True)
        self.sesion_bin.unlink(missing_ok=True)

    def restablecer(self):
        """Olvido de contraseña: se borra todo lo cifrado (no hay forma de recuperarlo sin la contraseña)."""
        for f in (self.archivo, self.secretos_bin, self.sesion_bin):
            f.unlink(missing_ok=True)
        self._llave = None


def _sid_usuario():
    """SID de la cuenta de Windows actual (más confiable que el nombre, que puede traer espacios o dominio)."""
    import subprocess
    r = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True,
                       creationflags=0x08000000)
    partes = [x.strip().strip('"') for x in r.stdout.strip().split('","')]
    return partes[-1] if partes and partes[-1].startswith("S-1-") else None


def _icacls(*args):
    import subprocess
    return subprocess.run(["icacls", *map(str, args)], capture_output=True, creationflags=0x08000000).returncode


def carpeta_accesible(carpeta):
    """¿La cuenta actual puede leer todo lo que hay en la carpeta?"""
    carpeta = Path(carpeta)
    try:
        if not carpeta.exists():
            return True
        for f in carpeta.iterdir():
            if f.is_file():
                with open(f, "rb"):
                    pass
        return True
    except PermissionError:
        return False


def proteger_carpeta(carpeta):
    """C: solo la cuenta de Windows actual (y SYSTEM) pueden entrar a la carpeta de datos.
    1) La carpeta deja de heredar permisos y recibe permisos explícitos (cuenta actual + SYSTEM), que se heredan.
    2) Lo que ya había dentro se «reinicia» para heredar esos permisos (si no, quedaría sin ningún permiso)."""
    sid = _sid_usuario()
    if not sid:
        return False
    carpeta = Path(carpeta)
    if _icacls(carpeta, "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "/grant:r", "*S-1-5-18:(OI)(CI)F", "/Q") != 0:
        return False
    if any(carpeta.iterdir()):
        _icacls(carpeta / "*", "/reset", "/T", "/C", "/Q")
    return carpeta_accesible(carpeta)


def reparar_carpeta(carpeta):
    """Versión 1.1 dejaba archivos sin permisos: el dueño restablece los permisos heredados y se vuelve a proteger."""
    carpeta = Path(carpeta)
    sid = _sid_usuario()
    if sid:
        _icacls(carpeta, "/grant", f"*{sid}:(OI)(CI)F", "/Q")
    _icacls(carpeta / "*", "/reset", "/T", "/C", "/Q")
    if not carpeta_accesible(carpeta) and sid:   # último recurso: tomar posesión de lo que hay dentro
        import subprocess
        subprocess.run(["takeown", "/F", str(carpeta), "/R", "/D", "S"], capture_output=True, creationflags=0x08000000)
        _icacls(carpeta, "/grant", f"*{sid}:(OI)(CI)F", "/T", "/C", "/Q")
    return proteger_carpeta(carpeta)
