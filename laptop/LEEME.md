# Laptop del profesor sin instalar nada (modo B, TC-20)

Todo corre desde esta carpeta: no se instala Python, Git ni nada en Windows.

1. **0_PREPARAR_LAPTOP.bat** (una sola vez, con internet): baja un Python 3.12 portátil a `laptop/python`
   e instala Django y las librerías de `requirements.txt` dentro de esa carpeta.
2. Copia en `laptop/datos/` el `.env` y el `db.sqlite3` del día (los genera el servidor central; **no se suben a Git**:
   llevan las claves de firma). El `.env` de la laptop lleva `MODO_LOCAL=1` y `CENTRAL_URL=<servidor central>`.
3. **1_ENCENDER_LAPTOP.bat**: enciende Django en `0.0.0.0:8000` y muestra la dirección para los celulares.
4. Al terminar, en el panel del profesor: «Terminar conferencia y sincronizar».
5. **2_CAMBIAR_URL_CENTRAL.bat** si cambia la dirección del servidor central.

Para dejar la laptop como estaba: quitar el permiso de Python en el firewall y borrar la carpeta.
