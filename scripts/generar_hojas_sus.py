"""Genera Hojas_SUS_Renueva_TI.docx: guía del moderador, una hoja por participante y el cuestionario SUS.
Uso: python scripts/generar_hojas_sus.py   (necesita python-docx)"""
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "..", "..", "Hojas_SUS_Renueva_TI.docx")

SUS = [
    "Creo que me gustaría usar este sistema con frecuencia.",
    "Encontré el sistema innecesariamente complejo.",
    "Pensé que el sistema era fácil de usar.",
    "Creo que necesitaría el apoyo de una persona técnica para poder usar este sistema.",
    "Encontré que las funciones del sistema estaban bien integradas.",
    "Pensé que había demasiada inconsistencia en este sistema.",
    "Imagino que la mayoría de las personas aprendería a usar este sistema muy rápido.",
    "Encontré el sistema muy incómodo de usar.",
    "Me sentí con mucha confianza al usar el sistema.",
    "Necesité aprender muchas cosas antes de poder empezar a usar este sistema.",
]
# Datos simulados que usa cada participante (NIP = 4 últimos dígitos del número, al revés)
PARTICIPANTES = [(f"P{i}", f"9966001{i}", f"{i}100", f"9966002{i}", f"{i}200") for i in range(1, 6)]
TAREAS = [
    ("T-1", "Regístrate en la conferencia con internet", "≤ 2 min, sin ayuda"),
    ("T-2", "Regístrate en modo avión (sin internet)", "≤ 2 min y explica qué pasó con su registro"),
    ("T-3", "Consulta tu estado en «Ver mi estado»", "≤ 1 min"),
]

d = Document()
for s in d.sections:
    s.left_margin = s.right_margin = Cm(2)
    s.top_margin = s.bottom_margin = Cm(1.8)
d.styles["Normal"].font.name = "Calibri"
d.styles["Normal"].font.size = Pt(11)


def tabla(cabeceras, filas, anchos=None):
    t = d.add_table(rows=1, cols=len(cabeceras))
    t.style = "Table Grid"
    for i, c in enumerate(cabeceras):
        t.rows[0].cells[i].text = c
        for r in t.rows[0].cells[i].paragraphs[0].runs:
            r.bold = True
    for fila in filas:
        celdas = t.add_row().cells
        for i, v in enumerate(fila):
            celdas[i].text = str(v)
    if anchos:
        for fila in t.rows:
            for i, a in enumerate(anchos):
                fila.cells[i].width = Cm(a)
    d.add_paragraph()
    return t


# ------------------------------------------------------------------ Guía del moderador
d.add_heading("Renueva TI · Prueba de usabilidad y SUS", 0)
d.add_paragraph("Caso TC-17 del plan de pruebas (NFR-01, FR-06). Métricas M4 (tiempo de registro) y M7 (SUS). "
                "Todos los datos que usan los participantes son simulados.")
d.add_heading("Guía del moderador", 1)
for t in [
    "Participantes: 5 alumnos que no hayan visto el sistema. Uno a la vez, con su propio celular y Chrome.",
    "Antes de empezar: enciende el servidor, el túnel HTTPS y abre el panel del profesor con el QR en la laptop. "
    "La conferencia de prueba debe estar activa (si venció: manage.py flush --no-input y generar_datos).",
    "Dile al participante: «Vas a registrar tu asistencia a una conferencia. No te voy a ayudar; di en voz alta lo "
    "que piensas. Estamos probando el sistema, no a ti».",
    "Entrégale solo su número de control y NIP de la tabla. No le expliques los pasos.",
    "Cronometra cada tarea desde que la página abre hasta que ve el resultado (folio o «Registro guardado "
    "localmente»). El cuestionario obliga a esperar 20 s por pregunta (100 s): anota el tiempo total y, si puedes, "
    "también el tiempo sin contar esa espera.",
    "Marca «Con ayuda» si tuviste que decirle qué tocar. Anota textualmente los comentarios y los errores.",
    "T-2: pídele que escanee el QR con internet, ponga modo avión y entonces responda y envíe. Al terminar, "
    "pregúntale: «¿Qué pasó con tu registro?» y anota si lo explicó bien.",
    "T-3: el código de 6 dígitos llega al correo del alumno; con datos simulados no llega a nadie, así que "
    "léeselo tú desde la pantalla «Avisos enviados» de Servicios Escolares.",
    "Al final de las tareas, que llene el cuestionario SUS sin que lo veas responder.",
]:
    d.add_paragraph(t, style="List Number")

d.add_heading("Datos simulados por participante", 2)
tabla(["Participante", "T-1: número de control", "T-1: NIP", "T-2: número de control", "T-2: NIP"],
      PARTICIPANTES)
d.add_paragraph("T-3 se hace con el mismo número de T-1.")

# ------------------------------------------------------------------ Una hoja por participante
for p, nc1, nip1, nc2, nip2 in PARTICIPANTES:
    d.add_page_break()
    d.add_heading(f"Participante {p}", 1)
    tabla(["Fecha y hora", "Carrera y semestre", "Celular (marca y modelo)", "Navegador", "Red (Wi-Fi o datos)"],
          [["", "", "", "", ""]])
    d.add_paragraph(f"Datos que se le entregan: T-1 y T-3 → {nc1} / NIP {nip1} · T-2 → {nc2} / NIP {nip2}")
    d.add_heading("Tareas", 2)
    tabla(["Tarea", "Qué hace", "Meta", "Tiempo total (min:s)", "¿Terminó? (Sí/No)", "¿Con ayuda? (Sí/No)",
           "Errores u observaciones"],
          [[c, q, m, "", "", "", "\n\n"] for c, q, m in TAREAS], anchos=[1.2, 3.6, 2.8, 2.0, 1.8, 1.8, 3.8])
    d.add_paragraph("T-2 · ¿Explicó que su registro quedó guardado y se enviará solo?   Sí ☐   No ☐")
    d.add_paragraph("Comentarios textuales del participante:")
    d.add_paragraph("\n\n\n")
    d.add_heading(f"Cuestionario SUS · {p}", 2)
    d.add_paragraph("Marca del 1 al 5 qué tan de acuerdo estás: 1 = totalmente en desacuerdo, "
                    "5 = totalmente de acuerdo.")
    tabla(["#", "Afirmación", "1", "2", "3", "4", "5"],
          [[i, t, "☐", "☐", "☐", "☐", "☐"] for i, t in enumerate(SUS, 1)], anchos=[0.8, 11.2, 1, 1, 1, 1, 1])

# ------------------------------------------------------------------ Concentrado
d.add_page_break()
d.add_heading("Concentrado de resultados", 1)
d.add_paragraph("Pasa aquí los resultados, o directamente al archivo sus_resultados.csv, y calcula con "
                "scripts/calcular_sus.py.")
tabla(["Part.", "T-1 (s)", "T-1 ok", "T-2 (s)", "T-2 ok", "T-3 (s)", "T-3 ok"] + [f"S{i}" for i in range(1, 11)],
      [[p] + [""] * 16 for p, *_ in PARTICIPANTES])
d.add_heading("Cómo se calcula el SUS (Brooke, 1996)", 2)
for t in ["Preguntas impares (1, 3, 5, 7, 9): respuesta − 1.", "Preguntas pares (2, 4, 6, 8, 10): 5 − respuesta.",
          "Suma los 10 valores y multiplica por 2.5: da un puntaje de 0 a 100 por participante.",
          "El SUS del sistema es el promedio de los 5 participantes. Meta del proyecto: 70 o más (M7).",
          "M4 y TC-17 se cumplen si al menos 4 de 5 completan T-1 en 2 minutos o menos sin ayuda."]:
    d.add_paragraph(t, style="List Bullet")
p = d.add_paragraph("Renueva TI · «Renovando Mundos, Renovándote a ti»")
p.alignment = WD_ALIGN_PARAGRAPH.CENTER

d.save(SALIDA)
print("Guardado:", os.path.abspath(SALIDA))
