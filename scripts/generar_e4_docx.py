"""Genera E4_Renueva_TI.docx usando el E3 como plantilla (portada, encabezado, pie y estilos).

  python scripts/generar_e4_docx.py

Las cifras vienen de las mediciones del 15 de noviembre de 2026 (pruebas automáticas,
prueba de carga, respaldo, contraste). Lo que solo puede hacer el consultor queda como [COMPLETAR].
"""
import copy
import os
import re

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, "..", ".."))          # carpeta Renueva_TI
EVID = os.path.join(AQUI, "..", "evidencias_e4")
PLANTILLA = os.path.join(RAIZ, "E3_Renueva_TI.docx")
SALIDA = os.path.join(RAIZ, "E4_Renueva_TI.docx")

NAVY, GRIS, CIAN = "00102E", "5A6475", "2DCAE3"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

d = docx.Document(PLANTILLA)
body = d.element.body

# ---------------------------------------------------------------- limpiar la plantilla
lista_pPr = copy.deepcopy(next(p for p in d.paragraphs if p.style.name == "List Paragraph")._p.pPr)
hijos = list(body)
fin_portada = next(i for i, el in enumerate(hijos) if el.find(f".//{W}sectPr") is not None)
for el in hijos[fin_portada + 1:]:
    if el.tag != f"{W}sectPr":
        body.remove(el)

CAMBIOS = {"ENTREGABLE E3": "ENTREGABLE E4",
           "Solución propuesta y plan de calidad": "Automatización funcionando, pruebas y resultados",
           "E3 · Solución propuesta y plan de calidad": "E4 · Automatización funcionando, pruebas y resultados"}


def reemplazar_textos(raiz):
    """Cambia solo los nodos de texto que contienen el texto viejo (no toca imágenes)."""
    for t in raiz.iter(f"{W}t"):
        for viejo, nuevo in sorted(CAMBIOS.items(), key=lambda kv: -len(kv[0])):
            if t.text and viejo in t.text:
                t.text = t.text.replace(viejo, nuevo)


for p in d.paragraphs[:3]:
    reemplazar_textos(p._p)
# encabezados y pies: se recorren las partes existentes, sin crear nuevas
for rel in d.part.rels.values():
    if rel.reltype.endswith(("/footer", "/header")):
        reemplazar_textos(rel.target_part.element)


# ---------------------------------------------------------------- utilidades de formato
def _run(p, texto, negrita=False, color=None, tam=None, cursiva=False):
    partes = re.split(r"(\*\*[^*]+\*\*)", texto)
    for parte in partes:
        if not parte:
            continue
        b = negrita or (parte.startswith("**") and parte.endswith("**"))
        r = p.add_run(parte.strip("*") if parte.startswith("**") else parte)
        r.bold = b
        r.italic = cursiva
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        if tam:
            r.font.size = Pt(tam)
    return p


def h1(texto):
    d.add_paragraph(texto, style="Heading 1")


def h2(texto):
    d.add_paragraph(texto, style="Heading 2")


def par(texto, alinear=True):
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.2
    if alinear:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return _run(p, texto)


def vinetas(items):
    for it in items:
        p = d.add_paragraph()
        p._p.insert(0, copy.deepcopy(lista_pPr))
        _run(p, it)


def nota(texto):
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    _run(p, texto, color=GRIS, tam=8.5, cursiva=True)


def pie_figura(texto):
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(5)
    _run(p, texto, color=GRIS, tam=8, cursiva=True)


def figura(archivo, ancho_cm, texto):
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(os.path.join(EVID, archivo), width=Cm(ancho_cm))
    pie_figura(texto)


def _celda(cell, texto, cabecera=False, negrita=False, fondo=None):
    tcPr = cell._tc.get_or_add_tcPr()
    bordes = OxmlElement("w:tcBorders")
    for lado in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{lado}")
        e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:space"), "0"); e.set(qn("w:color"), "C7D0DC")
        bordes.append(e)
    tcPr.append(bordes)
    if cabecera or fondo:
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), NAVY if cabecera else fondo)
        tcPr.append(shd)
    mar = OxmlElement("w:tcMar")
    for lado, v in (("top", 60), ("left", 100), ("bottom", 60), ("right", 100)):
        e = OxmlElement(f"w:{lado}"); e.set(qn("w:w"), str(v)); e.set(qn("w:type"), "dxa"); mar.append(e)
    tcPr.append(mar)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.04
    lineas = str(texto).split("\n")
    for k, linea in enumerate(lineas):
        if k:
            p = cell.add_paragraph(); p.paragraph_format.space_after = Pt(0)
        _run(p, linea, negrita=cabecera or negrita, color="FFFFFF" if cabecera else NAVY, tam=8.5)


def tabla(cabecera, filas, anchos=None, primera_negrita=True, colores=None):
    t = d.add_table(rows=1, cols=len(cabecera))
    t.autofit = False
    for j, c in enumerate(cabecera):
        _celda(t.rows[0].cells[j], c, cabecera=True)
    tr = t.rows[0]._tr
    trPr = tr.get_or_add_trPr(); th = OxmlElement("w:tblHeader"); th.set(qn("w:val"), "true"); trPr.append(th)
    for i, fila in enumerate(filas):
        celdas = t.add_row().cells
        for j, v in enumerate(fila):
            fondo = None
            if colores and j == colores[0]:
                fondo = {"Aprobado": "D6F3E4", "Cumplida": "D6F3E4", "Cumplido": "D6F3E4", "Corregido": "D6F3E4",
                         "Parcial": "FFF1C9", "Pendiente": "FDECE8", "No cumplida": "FDECE8"}.get(str(v).split(" ")[0])
            _celda(celdas[j], v, negrita=(j == 0 and primera_negrita), fondo=fondo)
    if anchos:
        for fila in t.rows:
            for j, a in enumerate(anchos):
                fila.cells[j].width = Cm(a)
    d.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ============================================================== CONTENIDO
h1("Cumplimiento de los requisitos del E4")
par("Este entregable presenta la automatización de Renueva TI funcionando con datos simulados para el proceso "
    "«Validación, concentración y registro de créditos académicos por asistencia al Congreso Académico», los "
    "casos de prueba ejecutados con sus resultados, las métricas medidas y el plan de la prueba de usabilidad. "
    "Parte del prototipo navegable del E3, que se conserva sin cambios, y lo convierte en una aplicación real.")
tabla(["Requisito del E4", "Dónde se cumple", "Estado"], [
    ["Automatización o prototipo funcional con datos simulados", "Sección 1 (enlace, repositorio y video en 1.6)", "Cumplido · enlace y video [COMPLETAR]"],
    ["Casos de prueba ejecutados con sus resultados", "Sección 2: 20 casos del E3, 25 pruebas automáticas y registro de defectos", "Parcial: 18 aprobados, 1 parcial (TC-20) y 1 pendiente (TC-17)"],
    ["Prueba de usabilidad con al menos 5 usuarios reales y SUS", "Sección 3: protocolo, tareas, cuestionario y hoja de resultados", "Pendiente: la aplica el consultor"],
    ["Métricas medidas antes y después", "Sección 4: 9 métricas", "Parcial: 7 medidas, 2 por medir con usuarios"],
    ["Borrador completo del libro con todas las secciones", "Sección 5: estado de las secciones 0 a 15", "Parcial: se integra para la entrega final"],
], anchos=[5.5, 7.0, 4.5], colores=(2,))
nota("Todos los datos de alumnos, profesores y personal son simulados. Las cifras marcadas como «medido» salen de "
     "ejecuciones reales del prototipo el 15 de noviembre de 2026; nada se presenta como medido si no se midió.")

# ---------------------------------------------------------------- 1
h1("1. La automatización funcionando")
h2("1.1 Qué se construyó")
par("Renueva TI construyó una aplicación web en Python (Django) con cuatro roles, más un servicio de avisos por "
    "WhatsApp. Cubre el flujo completo del TO-BE del E3: el alumno se registra con el QR, con o sin internet; el "
    "sistema valida cada registro con las cuatro reglas; el Comité Académico revisa el tablero y presiona «Enviar»; "
    "Servicios Escolares descarga el CSV para el SIIC y confirma la carga; y el alumno recibe el aviso.")
tabla(["Rol", "Pantallas construidas", "Qué puede hacer"], [
    ["Alumno (celular)", "A1 Inicio · A2 Identificación · A3 Cuestionario · A4a Folio · A4b Guardado local · A5 Mi estado",
     "Registrarse por QR, confirmar su identidad con su nombre parcial, responder el cuestionario, registrarse sin internet y consultar su estado con un código enviado a su correo."],
    ["Profesor designado", "P1 Panel de la conferencia",
     "Mostrar el QR firmado que cambia cada minuto, ver los registros que llegan, registrar a un alumno con apoyo y sincronizar en modo red local."],
    ["Comité Académico", "C1 Conferencias · C2 Tablero por carrera · C3 Detalle · Bitácora",
     "Crear conferencias con su cuestionario, revisar el estado por carrera, abrir alumno por alumno y enviar los válidos."],
    ["Servicios Escolares", "S1 Lotes y padrón · Detalle del lote · Avisos · Bitácora",
     "Cargar el padrón, descargar el CSV para el SIIC, confirmar la carga o reportar una falla, y revisar los avisos enviados."],
], anchos=[3.2, 6.3, 7.5])

h2("1.2 Herramientas implementadas frente a lo decidido en el E3")
par("Se respetó la pila elegida en el E3. Los cambios salieron de las pruebas y se documentan con su motivo.")
tabla(["Necesidad (E3)", "Elegida en el E3", "Implementado en el E4", "Cambio y motivo"], [
    ["N1 Servidor", "Django", "Django 5.2", "Sin cambio."],
    ["N2 Base de datos", "SQLite", "SQLite en modo WAL con transacciones IMMEDIATE", "Ajuste: la prueba de carga (TC-18) mostró bloqueos con 200 registros simultáneos (defecto D-02)."],
    ["Servidor web", "No se definió", "waitress (WSGI, Python puro)", "Nuevo: el servidor de desarrollo de Django no soporta 200 conexiones simultáneas (D-02). Gratuito y funciona en Windows."],
    ["N3 App sin internet", "PWA", "PWA con Service Worker y manifiesto instalable", "Sin cambio."],
    ["N4 Cola local", "IndexedDB", "IndexedDB sin bibliotecas externas", "Sin la biblioteca de apoyo prevista: el envoltorio propio ocupa 80 líneas."],
    ["N5 QR", "qrcode + HMAC", "qrcode 8.0 + HMAC-SHA256", "Sin cambio."],
    ["N7 Correo", "SMTP institucional (Gmail de pruebas en el prototipo)", "SMTP de Gmail de pruebas; sin credenciales, los correos se guardan en archivos", "Sin cambio. Envío real pendiente de la cuenta de pruebas."],
    ["N8 WhatsApp", "Biblioteca no oficial de WhatsApp Web", "whatsapp-web.js 1.34.8 en un servicio Node.js 26", "Sin cambio. Django le habla por HTTP local con un token."],
    ["N10 Versiones", "Git + GitHub", "Git listo (.gitignore); repositorio [COMPLETAR]", "Pendiente de crear el repositorio del consultor."],
    ["N11 Pruebas", "unittest de Django", "unittest de Django (25 pruebas) + Playwright para el recorrido con capturas", "Nuevo: Playwright solo para generar evidencia; no forma parte del producto."],
], anchos=[2.8, 3.4, 4.6, 6.2])

h2("1.3 Seguridad de los avisos durante las pruebas")
par("Como las pruebas se harán con datos de distintos usuarios, el sistema tiene un **modo de prueba**: solo envía "
    "avisos reales a los correos y teléfonos de una lista blanca. A los demás se les registra el aviso como "
    "«simulado» y no sale nada. Así se evita escribir por error a personas reales. Además, el padrón simulado usa el "
    "dominio reservado ejemplo.test, que no puede recibir correos.")

h2("1.4 Cobertura de los requerimientos «Debe tener» (Must)")
par("Los 23 requerimientos Must del E2 están construidos. La columna «Evidencia» indica cómo se comprobó.")
must = [
    ["FR-01", "Crear conferencia y cuestionario", "C1", "TC-01 automática"],
    ["FR-02", "QR firmado por minuto", "P1", "TC-02 automática; 106 QR en el paquete de la conferencia de prueba"],
    ["FR-03", "Cargar padrón", "S1", "TC-03 automática"],
    ["FR-04", "Identificar al alumno", "A2", "TC-04 automática"],
    ["FR-05", "Cuestionario de un solo intento", "A3", "TC-05 automática"],
    ["FR-06", "Confirmación con folio", "A4a, A4b", "Recorrido con capturas (Figura 2)"],
    ["FR-08", "Tablero por carrera", "C2", "TC-11 automática"],
    ["FR-10", "Enviar registros válidos", "C2", "TC-12 automática"],
    ["FR-11", "CSV para el SIIC", "S1", "TC-13 automática; CSV de ejemplo en evidencias"],
    ["FR-12", "Confirmar carga o reportar falla", "S1", "TC-14 automática"],
    ["FR-13", "Aviso por correo", "Correo", "TC-14 automática; correo generado (Figura 7)"],
    ["FR-22", "Registro sin internet", "A4b", "Recorrido con capturas (Figura 3) y TC-07 en celular en modo avión (Figura 10)"],
    ["FR-23", "Sincronización automática", "A4b, A5", "TC-08 automática; recorrido con capturas"],
    ["FR-25", "Validación automática", "C3", "TC-09 automática (tabla de decisión)"],
    ["FR-26", "Crédito con 2 conferencias", "S1", "TC-10 automática"],
    ["NFR-01", "Registro en 2 min o menos", "A1–A4", "Pendiente: prueba con 5 alumnos (TC-17)"],
    ["NFR-02", "Celular sin instalar", "A1–A5", "Medido a 360 px en Chrome y Edge"],
    ["NFR-03", "Contraste y texto de 16 px", "A1–A5", "TC-19 medido tras corregir D-01 y D-10"],
    ["NFR-05", "3 s con 200 simultáneos", "API", "TC-18 medido: p95 de 1.78 s"],
    ["NFR-07", "Roles, HTTPS y QR firmado", "Todas", "TC-15 y TC-02 automáticas; HTTPS probado con túnel (TC-06 y TC-07)"],
    ["NFR-08", "Sin pérdida de registros", "BD", "TC-16 medido: 200 de 200 restaurados"],
    ["NFR-09", "Formato del CSV", "S1", "TC-13 automática"],
    ["NFR-11", "Operación sin conexión", "A4b", "TC-08 automática y TC-07 en celular en modo avión"],
]
tabla(["Requisito", "Qué cubre", "Pantalla", "Evidencia"], must, anchos=[1.8, 5.0, 2.2, 8.0])
par("De los 12 requerimientos Should también quedaron construidos: FR-07 registro asistido, FR-09 detalle por "
    "alumno, FR-14 aviso por WhatsApp, FR-15 aviso de registro no válido, FR-16 consulta con código de 6 dígitos, "
    "FR-18 bitácora, FR-24 sincronización del modo red local, FR-27 aviso de falla, FR-28 nombre parcial y NFR-04 "
    "mensajes claros. NFR-06 (disponibilidad) y NFR-10 (cuatro navegadores) se miden al publicarlo.")

h2("1.5 Recorrido de la solución")
figura("P1_panel_profesor.png", 15.5, "Figura 1. Panel del profesor (P1): QR firmado que cambia cada minuto y registro asistido.")
figura("fig_flujo_en_linea.png", 16.5, "Figura 2. Registro del alumno con internet: identificación con nombre parcial, folio y un registro no válido por responder demasiado rápido.")
figura("fig_flujo_sin_internet.png", 16.5, "Figura 3. Registro sin internet: se guarda en el celular y se envía solo al regresar la conexión.")
figura("C2_tablero_por_carrera.png", 15.5, "Figura 4. Tablero del Comité Académico por carrera (C2).")
figura("C3_detalle_por_carrera.png", 15.5, "Figura 5. Detalle alumno por alumno con aciertos, tiempo, origen y motivo (C3).")
figura("S1_carga_confirmada_recorte.png", 15.5, "Figura 6. Servicios Escolares: lote recibido, vista previa del CSV y carga confirmada (S1).")
figura("correo_credito_cargado.png", 14.0, "Figura 7. Correo que recibe el alumno cuando su crédito se carga en el SIIC (datos simulados).")
figura("Correo_Aviso_Creditos.png", 14.0, "Figura 8. Envío real (TC-14): aviso recibido en la cuenta institucional de prueba.")
figura("WhatsApp_Evidencia.png", 7.0, "Figura 9. Envío real (TC-14): aviso recibido por WhatsApp en el número de prueba.")
figura("Con_Internet.jpeg", 5.5, "Figura 10a. Celular con internet (TC-06): folio RT-26-00043.")
figura("Sin_Internet.jpeg", 5.5, "Figura 10b. Celular sin conexión (TC-07): la app conserva el folio RT-26-00044 y lo muestra sin internet.")
figura("pantalla_profesor.jpeg", 15.5, "Figura 10c. Panel del profesor con los dos registros hechos desde el celular.")

h2("1.6 Enlace, repositorio y video")
tabla(["Elemento", "Dónde"], [
    ["Código fuente", "Carpeta prototipo_funcional/ · Repositorio GitHub: [COMPLETAR enlace]"],
    ["Prototipo en línea", "[COMPLETAR: enlace público con HTTPS, PythonAnywhere o túnel]"],
    ["Video de demostración", "[COMPLETAR: enlace al video corto del recorrido de la sección 1.5]"],
    ["Cómo ejecutarlo", "README.md: iniciar_servidor.bat e iniciar_whatsapp.bat; usuarios de demostración comite, profesor y servicios"],
], anchos=[4.0, 13.0])

# ---------------------------------------------------------------- 2
h1("2. Casos de prueba ejecutados")
par("Los casos son los del plan de pruebas del E3 (ISO/IEC/IEEE 29119). Se ejecutaron el 15 de noviembre de 2026. "
    "«Aprobado» significa que se ejecutó y dio el resultado esperado; «Parcial», que se ejecutó solo una parte del "
    "entorno previsto; «Pendiente», que necesita usuarios o equipos que aún no participan.")
casos = [
    ["TC-01", "FR-01, RN-03", "2 créditos se guardan; 3 se rechazan; sin cuestionario se rechaza", "Aprobado"],
    ["TC-02", "FR-02, RN-11", "QR vigente aceptado; 16 min después del fin y antes del inicio rechazados; QR alterado y de otro minuto rechazados", "Aprobado"],
    ["TC-03", "FR-03", "3 filas aceptadas; filas 5 y 6 rechazadas con su motivo; columna faltante avisada", "Aprobado"],
    ["TC-04", "FR-04, FR-28, RN-09", "Número válido muestra «M* S*»; inexistente explica qué revisar; ya registrado muestra su folio", "Aprobado"],
    ["TC-05", "FR-05, RN-09", "Incompleto no se envía; completo guarda el tiempo; segundo intento devuelve el primer registro", "Aprobado"],
    ["TC-06", "FR-06, NFR-05", "Folio en red local: p95 de 1.78 s con 200 simultáneos. En celular (Xiaomi Redmi Note 9S, Chrome, Telcel, por túnel HTTPS): 1.85 s de «Enviar» al folio RT-26-00043, medido con cronómetro el 15 nov", "Aprobado"],
    ["TC-07", "FR-22, NFR-11", "Sin internet simulado en el navegador: «Registro guardado localmente». Celular en modo avión (Xiaomi Redmi Note 9S, Chrome): el registro se capturó a las 17:12:44 sin conexión y llegó solo al servidor a las 17:13:26 al quitar el modo avión (folio RT-26-00044, válido, sin duplicados)", "Aprobado"],
    ["TC-08", "FR-23, NFR-11", "4 registros reenviados 3 veces: llegan 4, sin duplicados", "Aprobado"],
    ["TC-09", "FR-25, RN-09, RN-11, RN-14, RN-15", "49 % no válido y 50 % válido; 19.8 s no válido y 20 s válido por pregunta; fuera de ventana y duplicado con su motivo", "Aprobado"],
    ["TC-10", "FR-26, RN-13, FR-16", "1 conferencia sin crédito; 2 con crédito; la consulta del alumno no muestra el mínimo", "Aprobado"],
    ["TC-11", "FR-08, FR-09", "La suma de los estados coincide con el total en cada carrera; el detalle muestra el motivo", "Aprobado"],
    ["TC-12", "FR-10, RN-10", "Solo se envían válidos; el segundo clic no crea otro lote; queda en la bitácora", "Aprobado"],
    ["TC-13", "FR-11, NFR-09", "CSV UTF-8 con las 17 columnas y una fila por registro; con columna vacía se bloquea y lista la fila", "Aprobado"],
    ["TC-14", "FR-12, FR-13, FR-14, FR-27, RN-16", "Lógica aprobada: correo y WhatsApp por alumno, motivo obligatorio, sin repetir avisos, error de WhatsApp registrado y correo enviado. Envío real el 15 nov: correo por Gmail (SMTP) a la cuenta institucional de prueba y WhatsApp a un número de prueba, ambos recibidos (Figuras 8 y 9); los otros 35 alumnos del lote quedaron como «simulado» por la lista blanca", "Aprobado"],
    ["TC-15", "NFR-07", "3 roles × 3 pantallas: 0 accesos indebidos; sin sesión redirige al inicio de sesión", "Aprobado"],
    ["TC-16", "NFR-08", "200 registros, respaldo, falla simulada (0 registros), restauración: 200 de 200", "Aprobado"],
    ["TC-17", "NFR-01, FR-06", "Prueba de usabilidad con 5 alumnos y SUS (sección 3)", "Pendiente"],
    ["TC-18", "NFR-05", "200 registros simultáneos, 3 corridas: 200 de 200 guardados, 100 % en 3 s o menos, p95 de 1.68 a 1.78 s", "Aprobado"],
    ["TC-19", "NFR-02, NFR-03", "360 px sin desbordes en Chrome 157 y Edge 157; contraste mínimo 4.63:1 (botón azul); texto mínimo de 16 px en las pantallas del alumno", "Aprobado (tras corregir D-01 y D-10)"],
    ["TC-20", "FR-24", "Laptop sin internet y 3 celulares en su red local: sin ejecutar, programada para el 17 nov. La sincronización está construida y usa la misma API idempotente de TC-08", "Parcial"],
]
tabla(["Caso", "Requisitos", "Resultado obtenido", "Estado"], casos, anchos=[1.4, 3.0, 9.6, 3.0], colores=(3,))
par("**Resumen:** 15 aprobados, 4 parciales y 1 pendiente. Los parciales y el pendiente dependen de equipos reales "
    "(celular en 4G y en modo avión, laptop como red local), de las cuentas de prueba de correo y WhatsApp, y de los "
    "usuarios de la prueba de usabilidad.")

h2("2.1 Pruebas automáticas")
par("Las 25 pruebas automáticas se ejecutan con «python manage.py test registro» y repiten los casos cada vez que "
    "cambia el código. Resultado de la última ejecución: **25 de 25 aprobadas** (64.6 s).")
tabla(["Grupo", "Pruebas", "Qué comprueban"], [
    ["TC01_Conferencia", "2", "Créditos 2 y 3; conferencia sin cuestionario"],
    ["TC02_QR", "3", "Un QR distinto por minuto; ventana; QR alterado o de otro minuto"],
    ["TC03_Padron", "2", "Filas válidas y rechazadas; columna faltante"],
    ["TC04_Identificacion", "1", "Nombre parcial; número inexistente; ya registrado"],
    ["TC05_Cuestionario", "1", "Incompleto; completo; segundo intento"],
    ["TC07_Asistido", "1", "Registro asistido exige motivo y queda marcado"],
    ["TC08_Sincronizacion", "1", "Reenvíos sin duplicados"],
    ["TC09_Validacion", "3", "Tabla de decisión, valores límite, tope de 5 min y aviso de no válido"],
    ["TC10_Credito", "2", "Crédito con 2 conferencias; el mínimo no se muestra; código de un solo uso"],
    ["TC11_Tablero", "1", "Suma por estado = total; motivo en el detalle"],
    ["TC12_Enviar", "1", "Solo válidos, una sola vez, en bitácora"],
    ["TC13_CSV", "2", "Columnas y filas; columna vacía bloquea"],
    ["TC14_Avisos", "4", "Correo y WhatsApp; falla con motivo; WhatsApp caído; modo de prueba"],
    ["TC15_Roles", "1", "0 accesos indebidos entre roles"],
], anchos=[4.2, 1.6, 11.2])

h2("2.2 Registro de defectos")
par("Cada defecto encontrado en las pruebas se registró y se corrigió antes de este entregable.")
tabla(["ID", "Defecto", "Detectado en", "Corrección", "Estado"], [
    ["D-01", "La etiqueta «Válido» tenía contraste de 4.45:1, menor al 4.5:1 de WCAG AA (NFR-03).", "TC-19", "Verde más oscuro (#18693F): 5.68:1.", "Corregido"],
    ["D-02", "Con el servidor de desarrollo y 200 registros simultáneos: p95 de 5.5 s, solo 42 % en 3 s o menos y 5 conexiones rechazadas (NFR-05).", "TC-18", "Servidor waitress y SQLite en modo WAL: p95 de 1.78 s, 0 errores.", "Corregido"],
    ["D-03", "El servicio de WhatsApp se desconectaba al iniciar: Chrome no acepta la ruta de la sesión con «N°5».", "Arranque del servicio", "La sesión se guarda en una ruta sin acentos (%LOCALAPPDATA%).", "Corregido"],
    ["D-04", "El servicio de WhatsApp no encontraba un navegador.", "Arranque del servicio", "Usa el Chrome o Edge que ya tiene la computadora.", "Corregido"],
    ["D-05", "En la simulación «sin internet», el envío en segundo plano mandaba el registro de todas formas.", "Recorrido con capturas", "La simulación ya no programa el envío en segundo plano.", "Corregido"],
    ["D-06", "Los archivos de la app se servían primero desde la memoria del celular; una corrección no llegaba a quien ya la tenía.", "Revisión de código", "Primero se piden a la red; sin red, se usa la copia guardada.", "Corregido"],
    ["D-07", "Textos secundarios de 14 px en las pantallas del alumno (NFR-03 pide 16 px de base).", "TC-19", "Textos del alumno a 16 px.", "Corregido"],
    ["D-08", "El panel del profesor mostraba «03:44 a.m. h».", "Revisión de capturas", "Hora en formato de 24 horas.", "Corregido"],
    ["D-09", "Una prueba de TC-09 usaba un tiempo mínimo mal calculado (defecto de la prueba, no del sistema).", "Pruebas automáticas", "Se corrigió el dato de la prueba.", "Corregido"],
    ["D-10", "La consola de Windows no podía mostrar el carácter «→» del comando de datos.", "generar_datos", "Se cambió por «->».", "Corregido"],
], anchos=[1.2, 6.0, 2.6, 5.2, 2.0], colores=(4,))
nota("Defectos encontrados: 10. Corregidos: 10. Abiertos de tipo Must: 0.")

# ---------------------------------------------------------------- 3
h1("3. Prueba de usabilidad y SUS")
par("La guía pide una prueba con al menos 5 usuarios reales, tareas concretas y el cuestionario SUS. Esta parte la "
    "aplica el consultor en persona; aquí queda el protocolo listo y la hoja para registrar los resultados.")
h2("3.1 Protocolo")
vinetas([
    "Participantes: 5 alumnos del Instituto o más, de al menos dos carreras. Se identifican como P1 a P5; no se guardan nombres ni números de control reales.",
    "Antes: explicar que es un trabajo escolar, pedir su permiso y aclarar que se evalúa el sistema, no a la persona.",
    "Datos: cada participante usa un número de control simulado (99660011 a 99660015) y su propio celular.",
    "Durante: no dar instrucciones. Cronometrar desde que escanea el QR hasta que ve su folio, y anotar dudas y errores.",
    "Después: aplicar el cuestionario SUS en papel o en un formulario.",
])
h2("3.2 Tareas y metas")
tabla(["Tarea", "Qué hace el participante", "Meta (E3)"], [
    ["T-1", "Registrarse en la conferencia con internet", "≤ 2 min; 4 de 5 sin ayuda"],
    ["T-2", "Registrarse sin internet (modo avión después de abrir la app)", "≤ 2 min; 5 de 5 explican que quedó guardado"],
    ["T-3", "Consultar su estado con el código de su correo", "≤ 1 min"],
    ["T-4 a T-7", "Profesor, Comité y Servicios Escolares (opcional, con personal del área)", "Según la tabla 5.3 del E3"],
], anchos=[2.0, 10.0, 5.0])
h2("3.3 Cuestionario SUS (Brooke, 1996)")
par("Escala de 1 (totalmente en desacuerdo) a 5 (totalmente de acuerdo).")
tabla(["#", "Afirmación"], [
    ["1", "Creo que me gustaría usar este sistema con frecuencia."],
    ["2", "El sistema me pareció innecesariamente complejo."],
    ["3", "El sistema me pareció fácil de usar."],
    ["4", "Creo que necesitaría ayuda de una persona con conocimientos técnicos para usarlo."],
    ["5", "Las funciones del sistema están bien integradas."],
    ["6", "Hay demasiadas inconsistencias en el sistema."],
    ["7", "Imagino que la mayoría de las personas aprendería a usarlo muy rápido."],
    ["8", "El sistema me pareció muy difícil de usar."],
    ["9", "Me sentí muy seguro al usar el sistema."],
    ["10", "Necesité aprender muchas cosas antes de poder usarlo."],
], anchos=[1.0, 16.0])
par("**Cálculo:** SUS = 2.5 × [Σ(respuestas impares − 1) + Σ(5 − respuestas pares)]. Va de 0 a 100; la meta es 70 o más.")
h2("3.4 Resultados")
tabla(["Participante", "Carrera", "T-1 (min)", "¿Sin ayuda?", "T-2 (min)", "T-3 (min)", "SUS", "Comentarios"],
      [[f"P{i}", "[COMPLETAR]", "", "", "", "", "", ""] for i in range(1, 6)] +
      [["Promedio", "", "", "_ de 5", "", "", "", ""]], anchos=[2.4, 2.4, 1.5, 1.7, 1.5, 1.5, 1.3, 4.7])

# ---------------------------------------------------------------- 4
h1("4. Métricas antes y después")
par("Son las nueve métricas del plan de calidad del E3. «Medido» indica una ejecución real del prototipo; "
    "«Contado» indica un conteo sobre los diagramas.")
tabla(["#", "Métrica", "Antes", "Meta", "Después", "Estado"], [
    ["M1", "Traspasos físicos de papel", "3 (Confirmado)", "0", "0 (contado en el BPMN TO-BE y en el sistema: no hay hojas)", "Cumplida"],
    ["M2", "Pasos hechos por el personal", "8", "≤ 8", "6 (contado)", "Cumplida"],
    ["M3", "Requerimientos Must con caso de prueba", "—", "100 %", "100 % (23 de 23)", "Cumplida"],
    ["M4", "Tiempo para registrar la asistencia", "Sin dato", "≤ 2 min", "[COMPLETAR con la sección 3]", "Pendiente"],
    ["M5", "Registros sin internet que llegan al servidor", "No aplica", "100 %", "100 % en navegador (recorrido y TC-08) y 1 de 1 en celular en modo avión (TC-07, llegó en 42 s)", "Cumplida"],
    ["M6", "Tiempo de confirmación con 200 registros", "Sin dato", "p95 ≤ 3 s", "p95 de 1.78 s; 100 % en ≤ 3 s (medido, red local, 3 corridas)", "Cumplida"],
    ["M7", "Usabilidad (SUS)", "—", "≥ 70", "[COMPLETAR con la sección 3]", "Pendiente"],
    ["M8", "Defectos encontrados y corregidos", "—", "0 abiertos Must", "10 encontrados, 10 corregidos, 0 abiertos (medido)", "Cumplida"],
    ["M9", "Trabajo de captura por cada 100 registros", "33 a 50 h de tecleo (Reportado, B1)", "Carga de un archivo", "0 h de tecleo: el CSV de 200 filas se generó y validó en 0.14 s (medido). Falta medir la carga del encargado en el SIIC", "Parcial"],
], anchos=[1.0, 3.6, 2.6, 2.2, 5.6, 2.0], colores=(5,))
nota("La prueba de carga se hizo en la red local de la laptop del consultor con 200 alumnos simulados enviando al "
     "mismo tiempo. Con un celular por internet (TC-06) el folio apareció en 1.85 s; es una sola medición con cronómetro.")

# ---------------------------------------------------------------- 5
h1("5. Estado del borrador del libro")
par("El libro final (18 de noviembre, 5:00 p.m.) reúne los entregables corregidos. Esta tabla muestra de dónde sale "
    "cada sección y qué falta.")
tabla(["#", "Sección del libro", "Fuente", "Estado"], [
    ["0", "Portada propia", "E1", "Lista"],
    ["1", "Ficha académica", "Nueva", "Datos de ejemplo; se llenan al integrar el libro"],
    ["2", "Índice", "Se genera al integrar", "Al integrar"],
    ["3", "Quiénes somos", "E1 §1–2", "Lista"],
    ["4", "Resumen ejecutivo", "Nueva, con las métricas del E4", "Por redactar al cerrar las métricas"],
    ["5–6", "El proceso y validación de la necesidad", "E1 §3–7 y costo de la no calidad del E3 §6.2", "Lista"],
    ["7–8", "Usuarios y requerimientos", "E2", "Lista"],
    ["9", "Solución propuesta", "E3 §2–5 y E4 §1", "Lista"],
    ["10", "Plan de calidad", "E3 §6", "Lista"],
    ["11", "Pruebas y resultados", "E4 §2–4", "Parcial: SUS y pruebas en celular"],
    ["12", "Conclusiones y recomendaciones", "Nueva", "Por redactar"],
    ["13", "Bitácora y madurez personal", "E3 §6.7–6.8 + bitácora que se lleva aparte", "Se inserta al integrar el libro"],
    ["14", "Declaración de uso de IA", "E3 + E4", "Parcial: revisión del consultor"],
    ["15", "Referencias", "E1 a E4", "Lista"],
    ["A", "Anexos", "Entrevistas (E1), manual de identidad, evidencia de presentación al área", "[COMPLETAR: evidencia de presentación al área]"],
], anchos=[1.0, 5.0, 6.5, 4.5])

# ---------------------------------------------------------------- 6
h1("6. Riesgos y pendientes")
tabla(["#", "Pendiente", "Quién", "Afecta a"], [
    ["1", "Publicar en un hosting con HTTPS permanente (PythonAnywhere); las pruebas en celular se hicieron con un túnel temporal", "Consultor", "NFR-06, NFR-10"],
    ["2", "Prueba de usabilidad con 5 alumnos y SUS", "Consultor", "TC-17, M4, M7"],
    ["3", "Laptop como red local con 3 celulares (programada para el 17 nov)", "Consultor", "TC-20"],
    ["4", "Confirmar con el Comité las reglas RN-13 a RN-15 (riesgo R8). El archivo se entrega en CSV por decisión del consultor; el formato puede cambiarse a decisión de la empresa (riesgo R7)", "Consultor y área", "FR-11, FR-25"],
    ["5", "Repositorio en GitHub y video de demostración", "Consultor", "Entrega final"],
], anchos=[0.8, 10.2, 2.8, 3.2])

# ---------------------------------------------------------------- IA y referencias
h1("Declaración de uso de IA")
par("En este entregable se usó Claude (Anthropic) como apoyo para programar el prototipo (Django, PWA y servicio de "
    "WhatsApp), escribir y ejecutar las pruebas automáticas, de carga y de contraste, tomar las capturas y redactar "
    "este documento. Las decisiones de diseño vienen del E3 y son del consultor. Las cifras de las secciones 2 y 4 "
    "salen de ejecuciones reales del prototipo; las que no se pudieron medir están marcadas como pendientes.")
tabla(["Revisión del consultor"], [["[COMPLETAR: qué revisaste, qué probaste tú mismo y qué corregiste]"]], anchos=[17.0])

h1("Referencias")
for ref in [
    "Brooke, J. (1996). SUS: A «quick and dirty» usability scale. En P. W. Jordan, B. Thomas, B. A. Weerdmeester y I. L. McClelland (Eds.), Usability evaluation in industry (pp. 189–194). Taylor & Francis.",
    "Django Software Foundation. (2025). Django documentation (versión 5.2). https://docs.djangoproject.com/en/5.2/",
    "ISO/IEC/IEEE. (2022). Software and systems engineering — Software testing — Part 1: General concepts (ISO/IEC/IEEE 29119-1:2022).",
    "MDN Web Docs. (s. f.). Service Worker API. https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API",
    "MDN Web Docs. (s. f.). IndexedDB API. https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API",
    "whatsapp-web.js. (s. f.). A WhatsApp client library for Node.js. https://wwebjs.dev/",
    "SQLite. (s. f.). Write-Ahead Logging. https://www.sqlite.org/wal.html",
    "W3C. (2018). Web Content Accessibility Guidelines (WCAG) 2.1. https://www.w3.org/TR/WCAG21/",
]:
    p = d.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.0)
    p.paragraph_format.first_line_indent = Cm(-1.0)
    p.paragraph_format.space_after = Pt(5)
    _run(p, ref, tam=9.5)

d.save(SALIDA)
print("Guardado:", SALIDA)
