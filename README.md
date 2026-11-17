# Renueva TI · Prototipo funcional (E4)

Registro de asistencia al Congreso Académico por QR, con validación automática, envío del Comité,
CSV para el SIIC y avisos por correo y WhatsApp. **Todos los datos son simulados.**

**Ver la interfaz sin instalar nada:**
[prototipo navegable en GitHub Pages](https://javiersan237.github.io/Registro_de_Creditos_Academicos/prototipo_frontend.html).
Elige un rol arriba (Alumno, Profesor, Comité, Servicios Escolares); en el celular simulado, el botón
«● En línea» permite probar el registro sin internet. Es solo navegación: no guarda ni envía datos.

Este repositorio parte de ese prototipo navegable del E3 (`prototipo_frontend.html`) y lo convierte
en una aplicación real con Django.

## Encender

1. `iniciar_servidor.bat` → Django en `http://127.0.0.1:8000`
2. `iniciar_whatsapp.bat` → servicio de WhatsApp en `http://127.0.0.1:3001` (la primera vez abre
   `http://127.0.0.1:3001/qr` y escanéalo con el WhatsApp **de pruebas**: Dispositivos vinculados →
   Vincular un dispositivo).

Usuarios de demostración (contraseña `Renueva2026!`): `comite`, `profesor`, `servicios`, `admin`.

## Recorrido de prueba (una vuelta completa)

| # | Rol | Acción | Requisitos |
|---|-----|--------|-----------|
| 1 | Profesor | Entra a *Profesor designado* y abre el panel de «Automatización de procesos con Python». Se ve el QR que cambia cada minuto. | FR-02 |
| 2 | Alumno | Escanea el QR (o usa «Abrir el registro en este dispositivo»), escribe `99660001` y su NIP `1234`, confirma «Hola, U\* P\*», responde y envía. Ve su folio. | FR-04, FR-05, FR-06, FR-28 |
| 3 | Alumno | Repite tocando «● En línea» para simular sin internet: ve «Registro guardado localmente»; al volver a tocar se envía solo. | FR-22, FR-23 |
| 4 | Comité | *Tablero por carrera* → revisa → abre una carrera → «Enviar a Servicios Escolares». | FR-08, FR-09, FR-10 |
| 5 | Servicios | Abre el lote → «Descargar CSV para el SIIC» → «Se cargó bien». | FR-11, FR-12, FR-26 |
| 6 | Alumno | Recibe el correo y el WhatsApp «Tu crédito ya está en el SIIC». | FR-13, FR-14 |

El alumno de prueba `99660001` ya tiene una conferencia válida de ayer; con la de hoy suma 2 y
obtiene el crédito (RN-13).

## Configuración (`.env`)

Copia `.env.example` a `.env`. Lo importante:

- `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`: Gmail de pruebas + contraseña de aplicación. Sin esto,
  los correos se guardan como archivos en `outbox/`.
- `WHATSAPP_ENABLED=1` cuando el servicio de WhatsApp esté vinculado.
- `NOTIF_MODO=prueba` + `NOTIF_LISTA_BLANCA_CORREOS` / `NOTIF_LISTA_BLANCA_TELEFONOS`: solo se envían
  avisos reales a esos destinos; al resto se les registra como «simulado».

Para poner tus datos en el alumno de prueba:

```
.venv\Scripts\python manage.py generar_datos --telefono 4880000000 --correo tu_correo@matehuala.tecnm.mx
```

## Identificación del alumno: número de control + NIP

El alumno entra con su número de control y su **NIP de 4 dígitos**, el mismo con el que entra al SIIC. Así no
basta conocer el número de control de un compañero para registrarlo.

- El NIP llega en el padrón que entrega Servicios Escolares (columna `nip`).
- No se guarda en claro: solo su HMAC-SHA256 con `NIP_KEY`. No va en el QR ni en el paquete del celular.
- Tras 5 intentos fallidos el alumno se bloquea 15 minutos (`NIP_MAX_INTENTOS`, `NIP_BLOQUEO_MIN`).
- Sin internet, el NIP viaja con el registro y se verifica al sincronizar; si es incorrecto, el registro se
  rechaza y el alumno ve el motivo. El registro asistido por el profesor no pide NIP.
- Datos de ejemplo: el alumno `99660001` usa el NIP `1234`; los demás, los 4 últimos dígitos de su número al
  revés (`99660002` → `2000`). El profesor designado y el grupo de ejemplo se ponen con `--docente` y `--grupo`, o con
  `DEMO_DOCENTE` y `DEMO_GRUPO` en `.env` (que no se sube a Git).

## Archivo para el SIIC

Se entrega en **CSV** por decisión del consultor, porque se convierte con facilidad a otros formatos. El formato
es un cambio que puede realizarse a decisión de la empresa: el separador y la codificación se cambian en `.env`
(`EXPORT_SEPARADOR`, `EXPORT_CODIFICACION`) y otro tipo de archivo se agrega en `registro/servicios.py`
(`generar_csv`) sin tocar el resto del sistema.

## Probar desde un celular

- **Misma red Wi-Fi:** abre `http://IP-DE-LA-LAPTOP:8000/app/`. Funciona en línea; el modo sin internet
  real necesita HTTPS (el navegador solo activa el Service Worker en páginas seguras).
- **Con HTTPS (para probar modo avión):** túnel gratuito `cloudflared tunnel --url http://localhost:8000`
  y agrega la dirección `https://…trycloudflare.com` a `CSRF_TRUSTED_ORIGINS` en `.env`.

- **Laptop del profesor sin internet (modo B, TC-20) sin instalar nada:** carpeta [`laptop/`](laptop/LEEME.md).
  `0_PREPARAR_LAPTOP.bat` baja un Python portátil dentro de esa carpeta; `1_ENCENDER_LAPTOP.bat` sirve el registro en la
  red local y el panel del profesor sincroniza con el servidor central al reconectar.

## Comandos

| Comando | Para qué |
|---------|----------|
| `python manage.py test registro -v 2` | 29 pruebas automáticas (TC-01 a TC-15 del E3) |
| `python manage.py generar_datos [--inicio 07:30 --fin 15:00]` | Padrón, usuarios, conferencias y registros simulados |
| `python manage.py respaldar` / `restaurar <archivo>` | Respaldo y restauración (NFR-08) |
| `python manage.py reenviar_avisos` | Reintenta avisos con error (CU-07 3a) |

## Estructura

```
renueva/            configuración de Django
registro/
  models.py         modelo de datos (E3 §3.4)
  firma.py          QR firmado HMAC-SHA256 que cambia cada minuto
  validacion.py     motor de validación (4 reglas) y acreditación
  servicios.py      casos de uso CU-02 a CU-07
  notificaciones.py correo y WhatsApp, con lista blanca y registro de errores
  api.py            API REST (E3 §3.5)
  views.py          pantallas del profesor, Comité y Servicios Escolares
  tests.py          pruebas automáticas
static/js/          app del alumno (PWA), IndexedDB y Service Worker
templates/registro/ pantallas
whatsapp_service/   servicio Node con whatsapp-web.js
```
