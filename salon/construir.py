"""Construye el instalador de la versión del salón.

  .venv\\Scripts\\python salon\\construir.py

1. PyInstaller → salon\\dist\\RegistroCreditos\\ (la ventana + Django + waitress)
2. Copia el servicio de WhatsApp (index.js, node_modules, wa_version) y node.exe
3. Inno Setup → salon\\dist\\Instalar_RegistroCreditos_TecNM.exe

Se construye en una carpeta temporal sin acentos ni «°» y al final se copia el resultado a salon\\dist.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALON = RAIZ / "salon"
OBRA = Path(tempfile.gettempdir()) / "RegistroCreditos_build"
DIST = SALON / "dist"
NODE = Path(r"C:\Program Files\nodejs\node.exe")
ISCC = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Inno Setup 6" / "ISCC.exe"


def paso(t):
    print(f"\n=== {t} ===", flush=True)


def main():
    paso("PyInstaller")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--workpath", str(OBRA / "work"), "--distpath", str(OBRA / "dist"),
                    str(SALON / "RegistroCreditos.spec")], check=True, cwd=RAIZ)
    app = OBRA / "dist" / "RegistroCreditos"
    interno = app / "_internal"

    paso("Servicio de WhatsApp y Node")
    ws = interno / "whatsapp_service"
    ws.mkdir(exist_ok=True)
    for f in ("index.js", "package.json"):
        shutil.copy2(RAIZ / "whatsapp_service" / f, ws / f)
    shutil.copytree(RAIZ / "whatsapp_service" / "wa_version", ws / "wa_version", dirs_exist_ok=True)
    shutil.copytree(RAIZ / "whatsapp_service" / "node_modules", ws / "node_modules", dirs_exist_ok=True)
    (interno / "node").mkdir(exist_ok=True)
    shutil.copy2(NODE, interno / "node" / "node.exe")

    paso("Inno Setup")
    subprocess.run([str(ISCC), f"/DOrigen={app}", f"/O{OBRA / 'instalador'}", str(SALON / "instalador.iss")], check=True)

    paso("Copiar a salon\\dist")
    DIST.mkdir(exist_ok=True)
    for f in (OBRA / "instalador").glob("*.exe"):
        shutil.copy2(f, DIST / f.name)
        print(f"{DIST / f.name}  ({f.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
