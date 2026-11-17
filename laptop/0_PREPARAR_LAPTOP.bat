@echo off
chcp 65001 >nul
title Renueva TI - preparar la laptop (una sola vez)
cd /d "%~dp0"
rem Baja un Python PORTATIL dentro de esta carpeta. No instala nada en Windows.
if exist "python\python.exe" if exist "python\Lib\site-packages\django" (
  echo  Ya estaba preparado. Sigue con 1_ENCENDER_LAPTOP.bat
  pause & exit /b 0
)
set CURL=%SystemRoot%\System32\curl.exe
set TAR=%SystemRoot%\System32\tar.exe
echo.
echo  1/4 Descargando Python 3.12 portatil (11 MB)...
"%CURL%" -L -s -o python.zip https://www.python.org/ftp/python/3.12.6/python-3.12.6-embed-amd64.zip || goto error
if not exist python mkdir python
"%TAR%" -xf python.zip -C python || goto error
del python.zip
echo  2/4 Configurando rutas...
> python\python312._pth (
  echo python312.zip
  echo .
  echo Lib\site-packages
  echo ..\..
  echo import site
)
echo  3/4 Descargando pip...
"%CURL%" -L -s -o python\get-pip.py https://bootstrap.pypa.io/get-pip.py || goto error
python\python.exe python\get-pip.py --no-warn-script-location -q || goto error
del python\get-pip.py
echo  4/4 Instalando Django y librerias DENTRO de la carpeta (1-2 min)...
python\python.exe -m pip install -q --no-warn-script-location -r ..\requirements.txt || goto error
echo.
echo  Listo. Ahora copia la carpeta "datos" del dia y abre 1_ENCENDER_LAPTOP.bat
pause & exit /b 0
:error
echo.
echo  Algo fallo (revisa el internet de la laptop) y vuelve a abrir este archivo.
pause & exit /b 1
