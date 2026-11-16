@echo off
chcp 65001 >nul
cd /d "%~dp0whatsapp_service"
echo Renueva TI - WhatsApp. Abre http://127.0.0.1:3001/qr para vincular el numero de pruebas.
start "" http://127.0.0.1:3001/qr
"C:\Program Files\nodejs\node.exe" index.js
pause
