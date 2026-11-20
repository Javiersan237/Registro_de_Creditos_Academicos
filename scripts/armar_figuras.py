"""Une las capturas del alumno en las figuras del E4 (fig_flujo_en_linea.png y fig_flujo_sin_internet.png).

  python scripts/armar_figuras.py        (después de capturas_e4.py)
"""
import os

from PIL import Image, ImageDraw, ImageFont

EVID = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidencias_e4")
FUENTES = [r"C:\Windows\Fonts\Montserrat-Bold.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
ALTO_RECORTE = 1300          # las capturas del celular miden 780 × 1688; abajo solo hay blanco
SEP, MARGEN, ALTO_TITULO = 30, 30, 70

FIGURAS = {
    "fig_flujo_en_linea.png": [
        ("A1 Inicio", "A1_inicio.png"),
        ("A2 Número de control y NIP", "A2_identificacion_nip.png"),
        ("A2 Confirmación", "A2_identificacion_nombre_parcial.png"),
        ("A4a Folio", "A4a_confirmacion_folio.png"),
        ("A4a No válido", "A4a_no_valido_rapido.png"),
    ],
    "fig_flujo_sin_internet.png": [
        ("A1 Sin internet", "A1_sin_internet.png"),
        ("A4b Guardado en el celular", "A4b_guardado_localmente.png"),
        ("Envío al reconectar", "A4_envio_automatico_al_reconectar.png"),
        ("A5 Mi estado", "A5_mi_estado.png"),
    ],
}


def fuente(tam):
    for ruta in FUENTES:
        if os.path.exists(ruta):
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default()


for salida, paneles in FIGURAS.items():
    imgs = [Image.open(os.path.join(EVID, archivo)).convert("RGB") for _, archivo in paneles]
    imgs = [im.crop((0, 0, im.width, min(im.height, ALTO_RECORTE))) for im in imgs]
    ancho = MARGEN * 2 + sum(im.width for im in imgs) + SEP * (len(imgs) - 1)
    alto = MARGEN + ALTO_TITULO + max(im.height for im in imgs) + MARGEN
    lienzo = Image.new("RGB", (ancho, alto), "white")
    dib = ImageDraw.Draw(lienzo)
    f = fuente(38)
    x = MARGEN
    for (titulo, _), im in zip(paneles, imgs):
        dib.text((x + 6, MARGEN), titulo, font=f, fill="#00102E")
        lienzo.paste(im, (x, MARGEN + ALTO_TITULO))
        dib.rectangle((x, MARGEN + ALTO_TITULO, x + im.width - 1, MARGEN + ALTO_TITULO + im.height - 1), outline="#C7D0DC", width=2)
        x += im.width + SEP
    lienzo.save(os.path.join(EVID, salida), optimize=True)
    print("Guardada:", salida, lienzo.size)
