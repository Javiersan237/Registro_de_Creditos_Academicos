# PyInstaller: un solo programa (carpeta) con la ventana, el servidor Django y los datos de la app.
# Se construye con:  .venv\Scripts\python salon\construir.py
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(RAIZ, "templates"), "templates"),
    (os.path.join(RAIZ, "static"), "static"),
    (os.path.join(RAIZ, "salon", "icono.ico"), "salon"),
]
datas += collect_data_files("django")
datas += collect_data_files("tzdata")

hidden = (collect_submodules("django") + collect_submodules("registro") + collect_submodules("renueva")
          + collect_submodules("whitenoise") + collect_submodules("waitress")
          + collect_submodules("cryptography") + collect_submodules("sqlcipher3")
          + ["dotenv", "qrcode", "qrcode.image.svg", "requests", "tzdata", "boveda"])

a = Analysis(
    [os.path.join(RAIZ, "salon", "lanzador.py")],
    pathex=[RAIZ, os.path.join(RAIZ, "salon")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["numpy", "matplotlib", "PIL", "pytest"],
    # Django busca comandos y migraciones en archivos .py reales: se copian también como fuente.
    module_collection_mode={"django": "pyz+py", "registro": "py", "renueva": "py"},
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RegistroCreditos", console=False,
          icon=os.path.join(RAIZ, "salon", "icono.ico"), version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="RegistroCreditos")
