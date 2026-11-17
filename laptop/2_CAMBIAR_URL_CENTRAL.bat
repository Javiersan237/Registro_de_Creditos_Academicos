@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Usa esto solo si la direccion del tunel cambio.
set /p NUEVA= Pega la nueva direccion https://...trycloudflare.com y presiona Enter: 
if "%NUEVA%"=="" exit /b
"python\python.exe" -c "import sys,pathlib;u=sys.argv[1].strip().rstrip('/');[ (lambda p: p.write_text(''.join(('CENTRAL_URL='+u+'\n') if l.startswith('CENTRAL_URL=') else l for l in p.read_text(encoding='utf-8').splitlines(True)),encoding='utf-8'))(pathlib.Path(f)) for f in ('datos/.env','../.env') if pathlib.Path(f).exists()];print(' Listo: CENTRAL_URL='+u)" "%NUEVA%"
echo  Cierra la ventana del servidor y vuelve a abrir 1_ENCENDER_LAPTOP.bat
pause
