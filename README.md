# Registro de créditos por asistencia al Congreso Académico · prototipo de Renueva TI

> **Documento vivo.** Este README se actualiza conforme avanza el proyecto; no es la versión definitiva.
> Última actualización: 25 de noviembre de 2026 (correcciones de la auditoría de código).

Registro de asistencia al Congreso Académico con QR, con validación automática, envío del Comité Académico,
archivo CSV para el SIIC y avisos al alumno. Prototipo escolar de la práctica «Automatiza tu Tec»
(Fundamentos de Ingeniería de Software). **Todos los datos son simulados**: el repositorio no contiene nombres,
teléfonos, correos ni contraseñas reales.

- **Prototipo navegable (E3, solo interfaz):**
  [GitHub Pages](https://javiersan237.github.io/Registro_de_Creditos_Academicos/prototipo_frontend.html).
- **Demostración en línea (PythonAnywhere):** pendiente de actualizar a esta versión, una vez que la valide el equipo.

## Cómo funciona (flujo completo)

| # | Quién | Qué hace |
|---|-------|----------|
| 1 | Comité Académico | Crea la conferencia con su cuestionario y le asigna un profesor. |
| 2 | Profesor designado | Abre el panel de **su** conferencia y proyecta el QR firmado, que cambia cada minuto. |
| 3 | Alumno | Escanea el QR, escribe su número de control, su NIP de 4 dígitos y su WhatsApp, y contesta el cuestionario. Sin internet, el registro se guarda en el celular y se envía solo al volver la señal. |
| 4 | Sistema | Valida cada registro con 5 reglas (abajo) y avisa al alumno. |
| 5 | Comité Académico | Revisa el tablero por carrera y presiona «Enviar a Servicios Escolares». |
| 6 | Servicios Escolares | Descarga el CSV para el SIIC y confirma la carga (o reporta una falla). |
| 7 | Alumno | Recibe el aviso «Tu crédito ya está en el SIIC». |

### Reglas de validación (`registro/validacion.py`)

Se revisan en orden; el primer motivo que falla queda registrado:

1. **Ventana del QR:** el minuto que lleva el QR está entre el inicio y el fin + tolerancia (15 min por defecto).
2. **Hora de llegada:** el registro llega al servidor a más tardar «margen de envío» minutos (10 por defecto)
   después de ese cierre. Así una foto del QR no sirve horas después, y los registros hechos sin internet deben
   sincronizarse a tiempo. Ejemplo: conferencia de 10:00 a 11:00 → QR válido hasta 11:15 → el registro debe llegar
   antes de las 11:25. La laptop del profesor (modo B) queda exenta porque ella recibió el registro a tiempo.
3. **Un solo registro** por alumno y conferencia.
4. **Tiempo mínimo** de respuesta: 20 s por pregunta, nunca más de 5 minutos.
5. **Aciertos:** 50 % o más.

Todos los valores se cambian en `/admin/` → «Configuración de reglas».

## Dos formas de usarlo

### A. Laptop del salón (instalador, sin consolas)

Carpeta `salon/`. Un programa de escritorio con botones para encender el servidor y el WhatsApp, y apagar todo.
La base de datos va **cifrada completa con SQLCipher**; las claves y la sesión de WhatsApp van en una bóveda
(AES-256 + DPAPI de Windows + contraseña de administrador). Instrucciones: `salon/LEEME - Instalacion y uso.txt`.
El instalador se construye con `salon/construir.py` (PyInstaller + Inno Setup) y se publica en GitHub Releases.

### B. Desarrollo en la computadora

1. `python -m venv .venv` y `.venv\Scripts\pip install -r requirements.txt`
2. Copia `.env.example` a `.env` y llena lo necesario.
3. `.venv\Scripts\python manage.py migrate`
4. Datos de prueba (opcional, ver abajo): `.venv\Scripts\python manage.py generar_datos`
5. `iniciar_servidor.bat` → `http://127.0.0.1:8000`
6. WhatsApp (opcional): `cd whatsapp_service && npm install`, luego `iniciar_whatsapp.bat` y escanear el QR en
   `http://127.0.0.1:3001/qr` con el número **de pruebas**.

## Usuarios y contraseñas

Hay cuatro usuarios: `profesor`, `comite`, `servicios` y `admin` (superusuario de `/admin/`).
**Cada uno tiene una contraseña distinta**, y la de `admin` es mucho más larga. Nunca se escriben en el repositorio:

- En desarrollo: se ponen en `.env` (`CLAVE_PROFESOR`, `CLAVE_COMITE`, `CLAVE_SERVICIOS`, `CLAVE_ADMIN`). Si faltan,
  `generar_datos` las inventa al azar y las muestra una sola vez al terminar.
- En la laptop del salón: las genera el programa, van cifradas en la bóveda y se ven con «Mostrar contraseña».

## Datos de prueba (`generar_datos`) · SOLO PARA PRUEBAS

`python manage.py generar_datos` crea un estado de demostración: usuarios, 60 alumnos simulados (`99660001` a
`99660060`, correos `@ejemplo.test`, sin teléfono), una conferencia de ayer con historial y una activa hoy.
**No es parte del uso diario**: reemplaza los datos de ejemplo y borra los avisos registrados. Se puede borrar en
cualquier momento y se recomienda no usarlo cuando el prototipo ya tenga datos propios.

- NIP de prueba: `99660001` usa `1234`; los demás, los 4 últimos dígitos de su número al revés (`99660002` → `2000`).
  Es una convención solo para pruebas; un padrón real trae el NIP de cada alumno.
- Profesor y grupo de ejemplo: «Profesor Demo 03» y grupo «A» (se cambian con `--docente` y `--grupo`).
- `--inicio 07:30 --fin 15:00` fija el horario de la conferencia de hoy.

## Identificación del alumno: número de control + NIP

- El NIP (4 dígitos, el mismo del SIIC) llega en el padrón que carga Servicios Escolares (columna `nip`).
- Se guarda como HMAC-SHA256 con `NIP_KEY`, nunca en claro. No va en el QR ni en el paquete del celular.
- Tras 5 intentos fallidos el alumno se bloquea 15 minutos. Los intentos se suman dentro de la base de datos,
  así que varios intentos al mismo tiempo cuentan todos.
- Sin internet, el celular **no tiene datos de alumnos**: el NIP viaja con el registro y se verifica al sincronizar.
- El registro asistido por el profesor no pide NIP y queda marcado como «asistido».
- Cada profesor solo ve y opera **sus** conferencias (las de otro profesor responden «no encontrada»).

## Avisos (WhatsApp y correo)

- Modo `prueba` (por defecto): solo salen avisos a la lista blanca y al número que el propio alumno escribió con
  su NIP verificado; los demás quedan como «simulados».
- Un mensaje de WhatsApp cada 4 s, para cuidar el número que envía.
- «Reintentar avisos» reenvía solo los que tuvieron error y los pendientes de hace más de 10 minutos (los recientes
  siguen en la fila de envío; reenviarlos duplicaría mensajes).
- `whatsapp_service/` usa whatsapp-web.js (biblioteca no oficial: riesgo de bloqueo del número).

## Archivo para el SIIC

CSV por decisión del consultor, porque se convierte con facilidad a otros formatos; el formato es un cambio que
puede realizarse a decisión de la empresa. Separador y codificación en `.env` (`EXPORT_SEPARADOR`,
`EXPORT_CODIFICACION`). Con UTF-8 lleva la marca BOM para que Excel muestre bien los acentos; con otra
codificación no. No se descarga si alguna fila tiene columnas obligatorias vacías.

## Integridad y respaldos

- **Base sin cifrar** (desarrollo, servidor central): cada registro lleva un sello HMAC y la bitácora va encadenada.
  «Verificar integridad» detecta registros o entradas **cambiados** por fuera de la app. No detecta que se borre
  un registro completo ni las últimas entradas de la bitácora.
- **Base cifrada** (laptop del salón): sin sellos; SQLCipher protege cada página del archivo y la verificación usa
  `PRAGMA cipher_integrity_check`, que detecta cualquier cambio o borrado.
- `python manage.py respaldar` / `restaurar <archivo>` (NFR-08): usan la conexión de Django (con la llave, si la base
  va cifrada) y guardan en `<carpeta de datos>/backups`. El respaldo de una base cifrada queda cifrado.

## Logos e íconos de la institución

Los logos del TecNM y del Instituto Tecnológico de Matehuala **no se publican** en este repositorio. Para correr o
construir la app, colócalos a mano en `static/img/tecnm.png`, `static/img/itmatehuala.png`,
`static/img/icon-192.png`, `static/img/icon-512.png` y `salon/icono.ico`. En el repositorio solo están los de
Renueva TI (`logo_horizontal.png`, `isotipo.png`).

## Comandos

| Comando | Para qué |
|---------|----------|
| `python manage.py test registro` | 50 pruebas automáticas |
| `python manage.py generar_datos` | Datos simulados (solo pruebas) |
| `python manage.py preparar_salon [--sin-datos]` | Conferencia de demostración del salón, abierta hasta las 23:59 |
| `python manage.py respaldar` / `restaurar <archivo>` | Respaldo y restauración (NFR-08) |
| `python manage.py reenviar_avisos` | Reintenta avisos con error o atorados |
| `python manage.py verificar_integridad` | Revisa sellos y bitácora (o el archivo cifrado) |

## Cómo está hecho con Django

Django es el framework web: recibe cada petición, la manda a una **vista** según `renueva/urls.py`, la vista lee o
guarda en la base con los **modelos** (`registro/models.py`) y responde con una **plantilla** de
`templates/registro/` que el **motor de plantillas de Django** convierte en el HTML final (`{% extends %}`,
`{% block %}`, `{% url %}`, `{% csrf_token %}`…). La app del alumno es la excepción a propósito: Django entrega la
página una vez y, desde ahí, sus pantallas las arma el celular con JavaScript, porque deben funcionar sin internet.

```
renueva/              configuración de Django (settings, urls) y backend de base cifrada (db_cifrada/)
registro/
  models.py           modelo de datos
  firma.py            QR firmado HMAC-SHA256 que cambia cada minuto
  validacion.py       motor de validación (5 reglas) y acreditación
  servicios.py        casos de uso (registro, envío, padrón, CSV, avisos)
  notificaciones.py   correo y WhatsApp, con lista blanca y registro de errores
  api.py              API JSON para la app del alumno
  views.py            pantallas del profesor, Comité y Servicios Escolares
  seguridad.py        límites de intentos por IP
  integridad.py       sellos / verificación del archivo cifrado
  respaldo.py         respaldo y restauración
  tests.py            pruebas automáticas
static/js/            app del alumno (PWA), IndexedDB y Service Worker
templates/registro/   plantillas de Django
whatsapp_service/     servicio Node con whatsapp-web.js
salon/                app de escritorio e instalador para la laptop del salón
laptop/               kit sin instalación para el modo B (E4)
scripts/              herramientas que generaron los documentos y evidencias del E4
```
