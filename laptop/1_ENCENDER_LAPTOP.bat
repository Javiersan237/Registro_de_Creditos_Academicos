@echo off
chcp 65001 >nul
title Renueva TI - laptop (modo B)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONDONTWRITEBYTECODE=1
if not exist "python\python.exe" ( echo  Primero abre 0_PREPARAR_LAPTOP.bat & pause & exit /b 1 )
if not exist "datos\.env" ( echo  Falta datos\.env. Copia la carpeta "datos" del dia que deja ENCENDER_TODO.bat en la PC. & pause & exit /b 1 )

rem Datos del dia (los prepara ENCENDER_TODO.bat en la PC)
copy /y "datos\.env" "..\.env" >nul
if exist "datos\db.sqlite3" (
  copy /y "datos\db.sqlite3" "..\db.sqlite3" >nul
  move /y "datos\db.sqlite3" "datos\db_usada.sqlite3" >nul
  echo  Datos del dia cargados.
)
if not exist "..\db.sqlite3" ( echo  Falta la base de datos. Copia la carpeta "datos" del dia. & pause & exit /b 1 )

echo.
echo  =====================================================================
echo   Direccion de esta laptop (la que empieza con 192.168, 10. o 172.20):
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=1" %%j in ("%%i") do echo      http://%%j:8000/login/
echo.
echo   Abre ESA direccion en el navegador de la laptop (no 127.0.0.1),
echo   entra como  profesor / Renueva2026!  y abre la conferencia de hoy.
echo   Si Windows pregunta por el firewall: "Permitir acceso".
echo   Para apagar: cierra esta ventana o presiona Ctrl+C.
echo  =====================================================================
echo.
cd ..
"laptop\python\python.exe" manage.py runserver 0.0.0.0:8000 --noreload
pause
