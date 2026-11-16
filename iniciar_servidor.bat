@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Renueva TI - servidor en http://127.0.0.1:8000  (Ctrl+C para detener)
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
pause
