"""Recorre el prototipo como lo harían los usuarios y toma las capturas de evidencia del E4.

  .venv\\Scripts\\python scripts\\capturas_e4.py

Requiere el servidor encendido en http://127.0.0.1:8000 y los datos de generar_datos.
Usa el Chrome instalado (Playwright, channel="chrome").
"""
import email
import sys
import glob
import os
import time
from email import policy

from playwright.sync_api import sync_playwright

B = "http://127.0.0.1:8000"
OUT = os.path.join(os.path.dirname(__file__), "..", "evidencias_e4")
os.makedirs(OUT, exist_ok=True)
PASS = "Renueva2026!"


def foto(page, nombre, full=False):
    ruta = os.path.join(OUT, nombre + ".png")
    page.screenshot(path=ruta, full_page=full)
    print("captura", nombre)


def login(ctx, usuario):
    p = ctx.new_page()
    p.goto(B + "/login/")
    p.fill("#id_username", usuario)
    p.fill("#id_password", PASS)
    p.press("#id_password", "Enter")
    p.wait_for_load_state("networkidle")
    return p


def responder(page, correctas=True):
    n = page.locator("#qs fieldset").count()
    for i in range(n):
        idx = 0 if correctas or i > 1 else 1
        page.locator(f"input[name=q{i}]").nth(idx).check()


def identificar(page, nc):
    page.click("#a1start")
    page.fill("#nc", nc)
    page.click("#a2next")
    page.wait_for_selector("#a2confirm", state="visible")


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome")
    escritorio = nav.new_context(viewport={"width": 1280, "height": 860}, device_scale_factor=1.5)
    movil = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)

    if '--desde-comite' in sys.argv:
        goto_comite = True
    else:
        goto_comite = False
    # P1 · panel del profesor
    if not goto_comite:
        prof = login(escritorio, "profesor")
        prof.goto(B + "/profesor/2/")
        prof.wait_for_selector("#qr svg")
        foto(prof, "P1_panel_profesor")
        url_qr = prof.get_attribute("#qrlink", "href")

        # Alumno C: responde demasiado rápido → no válido (FR-15, RN-15)
        c_ctx = nav.new_context(**movil)
        c = c_ctx.new_page()
        c.goto(url_qr)
        c.wait_for_selector("#a1start", state="visible")
        identificar(c, "99660005")
        c.click("#a2si")
        responder(c)
        c.click("#a3send")
        c.wait_for_selector("[data-screen=A4a].on")
        foto(c, "A4a_no_valido_rapido")

        # Alumno A: en línea, con calma (FR-04, FR-05, FR-06, FR-28)
        a_ctx = nav.new_context(**movil)
        a = a_ctx.new_page()
        a.goto(url_qr)
        a.wait_for_selector("#a1start", state="visible")
        foto(a, "A1_inicio")
        identificar(a, "99660001")
        foto(a, "A2_identificacion_nombre_parcial")
        a.click("#a2si")
        responder(a)
        foto(a, "A3_cuestionario", full=True)

        # Alumno B: sin internet (FR-22, FR-23)
        b_ctx = nav.new_context(**movil)
        b = b_ctx.new_page()
        b.goto(url_qr)
        b.wait_for_selector("#a1start", state="visible")
        b.click("#net")                      # simula que no hay señal
        foto(b, "A1_sin_internet")
        identificar(b, "99660003")
        b.click("#a2si")
        responder(b)

        print("esperando el tiempo mínimo de respuesta (RN-15: 5 preguntas × 20 s)…")
        time.sleep(105)

        a.click("#a3send")
        a.wait_for_selector("[data-screen=A4a].on")
        foto(a, "A4a_confirmacion_folio")

        b.click("#a3send")
        b.wait_for_selector("[data-screen=A4b].on")
        foto(b, "A4b_guardado_localmente")
        b.click("#net")                      # regresa la señal → se envía solo
        b.wait_for_selector("#toast", state="visible")
        foto(b, "A4_envio_automatico_al_reconectar")
        b.click("[data-screen=A4a].on [data-go=A5], [data-screen=A4b].on [data-go=A5]")
        b.wait_for_selector("[data-screen=A5].on")
        time.sleep(1)
        foto(b, "A5_mi_estado")

    # Comité: conferencias, tablero, detalle y envío (FR-01, FR-08, FR-09, FR-10)
    com = login(escritorio, "comite")
    com.goto(B + "/comite/")
    foto(com, "C1_conferencias", full=True)
    com.goto(B + "/comite/tablero/?conf=2")
    foto(com, "C2_tablero_por_carrera", full=True)
    com.goto(B + "/comite/tablero/SIS/")
    foto(com, "C3_detalle_por_carrera", full=True)
    com.goto(B + "/comite/tablero/")
    if com.get_by_role("button", name="Enviar a Servicios Escolares").is_enabled():
        com.get_by_role("button", name="Enviar a Servicios Escolares").click()
    com.wait_for_load_state("networkidle")
    foto(com, "C2_enviado_a_servicios", full=True)

    # Servicios Escolares: lote, CSV, confirmación y avisos (FR-11, FR-12, FR-13, FR-26)
    se = login(escritorio, "servicios")
    se.goto(B + "/servicios/")
    se.click("a[href^='/servicios/lote/']")
    se.wait_for_load_state("networkidle")
    foto(se, "S1_lote_recibido", full=True)
    with se.expect_download() as d:
        se.click("text=Descargar CSV para el SIIC")
    d.value.save_as(os.path.join(OUT, "ejemplo_siic_lote.csv"))
    se.click("text=Se cargó bien")
    se.wait_for_load_state("networkidle")
    time.sleep(3)
    se.reload()
    foto(se, "S1_carga_confirmada", full=True)
    se.goto(B + "/avisos/")
    foto(se, "S2_avisos", full=True)
    se.goto(B + "/bitacora/")
    foto(se, "S3_bitacora", full=True)

    # Correo que recibe el alumno (backend de archivo: outbox/)
    archivos = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "outbox", "*.log")), key=os.path.getmtime)
    for nombre, archivo in [("correo_credito_cargado", archivos[-1])] if archivos else []:
        with open(archivo, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        html = msg.get_body(preferencelist=("html",)).get_content()
        pc = escritorio.new_page()
        pc.set_content(f"<div style='padding:20px;background:#f3f6fa'><p style='font-family:Arial;color:#5A6475'>"
                       f"Para: {msg['To']}<br>Asunto: {msg['Subject']}</p>{html}</div>")
        foto(pc, nombre, full=True)

    nav.close()
print("Listo:", os.path.abspath(OUT))
