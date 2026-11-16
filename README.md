# Renueva TI · Prototipo funcional (E4)

Registro de asistencia al Congreso Académico por QR, con validación automática, envío del Comité,
CSV para el SIIC y avisos por correo y WhatsApp. **Todos los datos son simulados.**

Parte del prototipo navegable del E3 (`../prototipo_frontend.html`, que no se modifica) y lo convierte
en una aplicación real con Django.

## Encender

1. `iniciar_servidor.bat` → Django en `http://127.0.0.1:8000`
2. `iniciar_whatsapp.bat` → servicio de WhatsApp en `http://127.0.0.1:3001` (la primera vez abre
   `http://127.0.0.1:3001/qr` y escanéalo con el WhatsApp **de pruebas**: Dispositivos vinculados →
   Vincular un dispositivo).

Usuarios de demostración (contraseña `(contraseña retirada)`): `comite`, `profesor`, `servicios`, `admin`.

## Recorrido de prueba (una vuelta completa)

| # | Rol | Acción | Requisitos |
|---|-----|--------|-----------|
| 1 | Profesor | Entra a *Profesor designado* y abre el panel de «Automatización de procesos con Python». Se ve el QR que cambia cada minuto. | FR-02 |
| 2 | Alumno | Escanea el QR (o usa «Abrir el registro en este dispositivo»), escribe `99660001`, confirma «Hola, U\* P\*», responde y envía. Ve su folio. | FR-04, FR-05, FR-06, FR-28 |
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

## Probar desde un celular

- **Misma red Wi-Fi:** abre `http://IP-DE-LA-LAPTOP:8000/app/`. Funciona en línea; el modo sin internet
  real necesita HTTPS (el navegador solo activa el Service Worker en páginas seguras).
- **Con HTTPS (para probar modo avión):** túnel gratuito `cloudflared tunnel --url http://localhost:8000`
  y agrega la dirección `https://…trycloudflare.com` a `CSRF_TRUSTED_ORIGINS` en `.env`.

## Comandos

| Comando | Para qué |
|---------|----------|
| `python manage.py test registro -v 2` | 25 pruebas automáticas (TC-01 a TC-15 del E3) |
| `python manage.py generar_datos` | Padrón, usuarios, conferencias y registros simulados |
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
