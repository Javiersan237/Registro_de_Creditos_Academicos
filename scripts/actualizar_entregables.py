"""Aplica a E2 y E3 los ajustes de diseño (NIP del alumno, formato CSV, revisión del consultor).
Uso: python actualizar_entregables.py <carpeta_entrada> <carpeta_salida>
Es repetible: si un texto ya fue cambiado, lo salta."""
import copy
import os
import sys

import docx


def parrafos(d):
    vistos = set()
    for p in d.paragraphs:
        yield p
    for t in d.tables:
        for fila in t.rows:
            for c in fila.cells:
                if c._tc in vistos:
                    continue
                vistos.add(c._tc)
                for p in c.paragraphs:
                    yield p


def reemplazar_en(p, viejo, nuevo):
    """Reemplaza dentro del párrafo conservando el formato de cada tramo."""
    runs = p.runs
    texto = "".join(r.text for r in runs)
    i = texto.find(viejo)
    if i < 0:
        return False
    fin, pos, puesto = i + len(viejo), 0, False
    for r in runs:
        a, b = pos, pos + len(r.text)
        pos = b
        if b <= i or a >= fin:
            continue
        t = r.text
        ini, ter = max(i, a) - a, min(fin, b) - a
        r.text = t[:ini] + ("" if puesto else nuevo) + t[ter:]
        puesto = True
    return True


def aplicar(d, cambios):
    for viejo, nuevo in cambios:
        n = sum(1 for p in parrafos(d) if viejo in "".join(r.text for r in p.runs))
        if n == 0:
            ya = bool(nuevo) and any(nuevo in p.text for p in parrafos(d))
            print("   ya aplicado:" if ya or not nuevo else "   NO ENCONTRADO:", viejo[:70])
            if not ya and nuevo:
                raise SystemExit(1)
            continue
        if n > 1:
            raise SystemExit(f"Texto no único ({n}): {viejo[:70]}")
        for p in parrafos(d):
            if reemplazar_en(p, viejo, nuevo):
                break


def vineta_despues(d, ancla, titulo, cuerpo):
    if any(titulo in p.text for p in d.paragraphs):
        return
    for p in d.paragraphs:
        if ancla in p.text:
            nuevo = copy.deepcopy(p._p)
            p._p.addnext(nuevo)
            q = docx.text.paragraph.Paragraph(nuevo, p._parent)
            rs = q.runs
            if len(rs) > 1:
                rs[0].text = titulo
                rs[1].text = " " + cuerpo
                for r in rs[2:]:
                    r._r.getparent().remove(r._r)
            else:
                rs[0].text = titulo + " " + cuerpo
            return
    raise SystemExit("Ancla no encontrada: " + ancla)


E2 = [
    ("cargar y actualizar el padrón con nombre, número de control, carrera",
     "cargar y actualizar el padrón con nombre, número de control, NIP de 4 dígitos, carrera"),
    ("identificar al alumno por su número de control y validarlo contra el padrón",
     "identificar al alumno por su número de control y su NIP de 4 dígitos (el mismo con el que entra al SIIC) y "
     "validarlos contra el padrón"),
    ("2. Captura su número de control y el sistema le muestra",
     "2. Captura su número de control y su NIP de 4 dígitos, y el sistema le muestra"),
    ("2a. Número de control no encontrado: el sistema explica qué verificar.",
     "2a. Número de control no encontrado o NIP incorrecto: el sistema explica qué verificar y no muestra datos del alumno."),
    ("padrón (nombre, número de control, carrera, semestre, grupo, teléfono y correo)",
     "padrón (nombre, número de control, NIP, carrera, semestre, grupo, teléfono y correo)"),
    ("Dado un número de control que no está en el padrón, cuando",
     "Dado un número de control que no está en el padrón o un NIP que no corresponde, cuando"),
    ("Dado un número de control válido, cuando", "Dado un número de control y un NIP válidos, cuando"),
    ("después de capturar su número de control, para", "después de capturar su número de control y su NIP, para"),
    ("(nombre, clave, carrera, semestre, grupo, teléfono, correo)",
     "(nombre, clave, NIP, carrera, semestre, grupo, teléfono, correo)"),
    ("Formato exacto del archivo de carga al SIIC (columnas y codificación) y proceso de carga del encargado de captura.",
     "Proceso de carga del encargado de captura y si requiere un formato distinto al CSV. El CSV es decisión del "
     "consultor por ser fácil de convertir; el formato es un cambio que puede realizarse a decisión de la empresa."),
    ("debe cumplir el formato acordado con Servicios Escolares (columnas y codificación) y validarse",
     "debe cumplir el formato definido (CSV por decisión del consultor; puede cambiarse a decisión de la empresa), "
     "con sus columnas y codificación, y validarse"),
]

REVISION = (
    "Se revisó manualmente la información de las entregas, además de cambiar el texto escrito por elecciones hechas "
    "por el consultor para declarar qué elementos se toman para construir con facilidad el prototipo y tener un trabajo "
    "profesional terminado. No se sugiere que sea así en los apartados cambiados: son cambios que se hacen con el fin "
    "de que el lector entienda de mejor forma las mediciones y los cambios escritos, además de introducir las imágenes "
    "correspondientes y cambiar la arquitectura en cada fallo de iteración, en el dado caso de que la IA se quedara en "
    "un punto muerto.")

E3 = [
    ("El padrón trae nombre, clave de control, carrera",
     "El padrón trae nombre, clave de control, NIP de 4 dígitos (el mismo con el que el alumno entra al SIIC), carrera"),
    ("Escanea el QR, confirma su número de control (ve su nombre parcial) y responde",
     "Escanea el QR, escribe su número de control y su NIP de 4 dígitos (el mismo del SIIC), confirma su nombre "
     "parcial y responde"),
    ("Valida el registro: dentro de la ventana de tiempo",
     "Verifica el NIP del alumno y valida el registro: dentro de la ventana de tiempo"),
    ("la integración es un archivo CSV propuesto, que se confirmará con Servicios Escolares.",
     "la integración es un archivo CSV. El CSV es decisión del consultor porque se convierte con facilidad a otros "
     "formatos; el formato es un cambio que puede realizarse a decisión de la empresa."),
    ("lo reducen el cuestionario, el tiempo mínimo y el nombre parcial (riesgo R6)",
     "lo reducen el NIP, el cuestionario, el tiempo mínimo y el nombre parcial (riesgo R6)"),
    ("número de control, nombre, carrera, semestre, grupo, teléfono, correo institucional (datos simulados en el prototipo)",
     "número de control, NIP de 4 dígitos (guardado como hash), nombre, carrera, semestre, grupo, teléfono, correo "
     "institucional (datos simulados en el prototipo)"),
    ("Recibe un registro (token, respuestas, tiempo).",
     "Recibe un registro (token, número de control, NIP, respuestas, tiempo)."),
    ("Módulo csv de Python, UTF-8",
     "Módulo csv de Python, UTF-8; el formato se puede sustituir sin tocar el resto del sistema"),
    ("el número de control se valida y se confirma con el nombre parcial.",
     "el número de control y el NIP se validan y la identidad se confirma con el nombre parcial."),
    ("Número existente, inexistente y ya registrado en esa conferencia.",
     "Número existente con NIP correcto, con NIP incorrecto, número inexistente y ya registrado en esa conferencia."),
    ("Continúa con nombre parcial; explica qué verificar; muestra el folio existente.",
     "Continúa con nombre parcial; con NIP incorrecto no continúa ni muestra datos del alumno; explica qué verificar; "
     "muestra el folio existente."),
    ("Vigencia de 1 minuto, cuestionario, tiempo mínimo y nombre parcial.",
     "Vigencia de 1 minuto, NIP personal, cuestionario, tiempo mínimo y nombre parcial."),
    ("Confirmar columnas, separador y codificación (UTF-8) con el encargado; parámetros configurables.",
     "El CSV es decisión del consultor por ser fácil de convertir; el formato es un cambio que puede realizarse a "
     "decisión de la empresa: el exportador está separado del resto del sistema y sus columnas, separador y "
     "codificación son parámetros."),
    ("El padrón contiene datos personales (teléfono y correo).",
     "El padrón contiene datos personales (teléfono, correo y NIP)."),
    ("en producción, acceso por rol y uso limitado a este proceso.",
     "en producción, acceso por rol, NIP guardado como hash y uso limitado a este proceso."),
    ("Columnas, separador y codificación exactos del CSV que acepta el encargado del SIIC.",
     "Si el encargado del SIIC requiere un formato distinto al CSV o columnas adicionales; ese cambio queda a decisión "
     "de la empresa y no modifica el resto de la solución."),
    ("Entrega del padrón de alumnos (simulado en el prototipo) por parte de Servicios Escolares.",
     "Entrega del padrón de alumnos, con el NIP de cada alumno, por parte del encargado de Servicios Escolares "
     "(simulado en el prototipo)."),
    ("[COMPARTIR el enlace con el docente desde la página del prototipo antes de entregar]", ""),
    (" (a confirmar por el consultor)", ""),
    ("[como lo dice el nombre", "Como lo dice el nombre"),
    ("Correción de datos incorrectos, elementos con simbología fallida y secciones que no deben de aparecer en los "
     "avances dados.", REVISION),
]

if __name__ == "__main__":
    ent, sal = sys.argv[1], sys.argv[2]
    os.makedirs(sal, exist_ok=True)

    d = docx.Document(os.path.join(ent, "E2_Renueva_TI.docx"))
    print("E2")
    aplicar(d, E2)
    d.save(os.path.join(sal, "E2_Renueva_TI.docx"))

    d = docx.Document(os.path.join(ent, "E3_Renueva_TI.docx"))
    print("E3")
    aplicar(d, E3)
    for p in parrafos(d):  # bitácora PSP: celdas todavía sin dato
        if p.text.strip() == "[COMPLETAR]":
            reemplazar_en(p, "[COMPLETAR]", "Por registrar")
    vineta_despues(
        d, "QR firmado y de corta vida.", "Número de control y NIP.",
        "El alumno se identifica con su número de control y su NIP de 4 dígitos, el mismo con el que entra al SIIC y "
        "que el encargado de Servicios Escolares entrega en el padrón. Así no basta conocer el número de control de un "
        "compañero para registrarlo, y quien presta su NIP presta también su acceso al SIIC. El servidor guarda el NIP "
        "como hash, no lo incluye en el QR ni en el paquete del celular y bloquea por 15 minutos al alumno tras 5 "
        "intentos fallidos. Sin internet, el NIP viaja con el registro y se verifica al sincronizar; si es incorrecto, "
        "el registro se rechaza y el alumno ve el motivo.")
    d.save(os.path.join(sal, "E3_Renueva_TI.docx"))
    print("Listo en", sal)
