"""Calcula el SUS y los tiempos de la prueba de usabilidad (TC-17, M4, M7).

Uso: python scripts/calcular_sus.py [sus_resultados.csv]

Columnas del CSV (una fila por participante):
  participante, t1_seg, t1_ok, t1_ayuda, t2_seg, t2_ok, t2_explico, t3_seg, t3_ok, s1 ... s10
  - *_ok, *_ayuda, t2_explico: SI o NO.  - s1..s10: respuestas del 1 al 5.
"""
import csv
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, "..", "..", "sus_resultados.csv")


def si(v):
    return str(v).strip().upper() in ("SI", "SÍ", "S", "1", "X")


def sus(fila):
    r = [int(fila[f"s{i}"]) for i in range(1, 11)]
    if any(x < 1 or x > 5 for x in r):
        raise ValueError("Las respuestas del SUS van del 1 al 5")
    return sum((x - 1) if i % 2 == 0 else (5 - x) for i, x in enumerate(r)) * 2.5


with open(ruta, encoding="utf-8-sig", newline="") as f:
    filas = [x for x in csv.DictReader(f) if (x.get("s1") or "").strip()]
if not filas:
    sys.exit("El archivo no tiene participantes con respuestas todavía.")

puntajes = []
print(f"{'Part.':<6}{'T-1':>7}{'T-2':>7}{'T-3':>7}{'SUS':>8}")
for x in filas:
    p = sus(x)
    puntajes.append(p)
    print(f"{x['participante']:<6}{x['t1_seg'] or '—':>6}s{x['t2_seg'] or '—':>6}s{x['t3_seg'] or '—':>6}s{p:>8.1f}")
n = len(filas)
# Quien no tiene tiempo anotado (p. ej. P5) no entra al promedio de tiempos, igual que en generar_e4_docx.py
con_t1 = [x for x in filas if str(x.get("t1_seg") or "").strip()]
t1 = [int(x["t1_seg"]) for x in con_t1] or [0]
en_meta = sum(1 for x in con_t1 if si(x["t1_ok"]) and not si(x["t1_ayuda"]) and int(x["t1_seg"]) <= 120)
print(f"\nParticipantes: {n}")
print(f"SUS promedio (M7, meta >= 70): {sum(puntajes) / n:.1f}  (mínimo {min(puntajes):.1f}, máximo {max(puntajes):.1f})")
print(f"T-1 tiempo promedio (M4, meta <= 120 s): {sum(t1) / len(t1):.0f} s  (mínimo {min(t1)}, máximo {max(t1)}; "
      f"{len(con_t1)} de {n} con tiempo anotado)")
print(f"T-1 en 2 min o menos y sin ayuda (TC-17, meta 4 de 5): {en_meta} de {n}")
print(f"T-2 completaron: {sum(si(x['t2_ok']) for x in filas)} de {n}; explicaron que quedó guardado: "
      f"{sum(si(x['t2_explico']) for x in filas)} de {n}")
print(f"T-3 completaron: {sum(si(x['t3_ok']) for x in filas)} de {n}")
