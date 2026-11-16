"""Casos de uso del E2 (CU-02 a CU-07) como funciones, para que vistas, API y pruebas usen la misma lógica."""
import csv
import io
from collections import OrderedDict

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import firma, notificaciones, validacion
from .models import CARRERAS, CARRERAS_DICT, Alumno, Bitacora, Configuracion, Conferencia, Lote, Registro


class ErrorRegistro(Exception):
    """Error que se muestra al usuario tal cual (NFR-04: qué pasó + qué hacer)."""

    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------------------------------------------------------------- CU-02 / CU-03
def buscar_alumno(no_control):
    no_control = (no_control or "").strip()
    if not no_control.isdigit() or len(no_control) != 8:
        raise ErrorRegistro("El número de control debe tener 8 dígitos. Revísalo y vuelve a intentarlo.")
    try:
        return Alumno.objects.get(pk=no_control)
    except Alumno.DoesNotExist:
        raise ErrorRegistro("No encontramos ese número de control en el padrón. Revisa que esté bien escrito; "
                            "si es correcto, acude con el profesor de la conferencia.", 404)


def registrar_por_qr(*, uuid, token, no_control, respuestas, tiempo_seg, capturado_en=None,
                     origen=Registro.CELULAR):
    """CU-02. Idempotente: el mismo uuid devuelve el mismo registro (FR-23).
    Devuelve (registro, nuevo: bool, duplicado: bool)."""
    previo = Registro.objects.filter(uuid=uuid).first()
    if previo:
        return previo, False, False

    try:
        conferencia, minuto = firma.verificar(token)
    except firma.TokenInvalido as e:
        raise ErrorRegistro(str(e))
    alumno = buscar_alumno(no_control)

    existente = Registro.objects.filter(alumno=alumno, conferencia=conferencia).first()
    if existente:  # RN-09: se conserva el primero y se muestra su folio
        return existente, False, True

    if not isinstance(respuestas, list):
        raise ErrorRegistro("Las respuestas llegaron incompletas. Vuelve a enviar el cuestionario.")
    aciertos, total = validacion.calificar(conferencia, respuestas)
    if len(respuestas) < total or any(r is None for r in respuestas[:total]):
        raise ErrorRegistro("Faltan preguntas por responder. Contesta todas antes de enviar.")

    minuto_qr = firma.minuto_a_fecha(minuto)
    valido, motivo = validacion.evaluar(conferencia, minuto_qr, int(tiempo_seg or 0), aciertos, total, False)
    try:
        with transaction.atomic():
            registro = Registro.objects.create(
                uuid=uuid, alumno=alumno, conferencia=conferencia, token=token, minuto_qr=minuto_qr,
                respuestas=respuestas[:total], aciertos=aciertos, total=total,
                porcentaje=round(aciertos / total * 100, 1) if total else 0, tiempo_seg=int(tiempo_seg or 0),
                capturado_en=capturado_en, origen=origen, valido=valido, motivo=motivo)
    except IntegrityError:  # dos envíos simultáneos del mismo alumno
        return Registro.objects.get(alumno=alumno, conferencia=conferencia), False, True

    if not valido:  # FR-15
        asunto, texto = notificaciones.msg_registro_no_valido(registro)
        notificaciones.notificar(alumno, "no_valido", asunto, texto)
    return registro, True, False


def registrar_asistido(*, conferencia, no_control, motivo, usuario):
    """CU-03 / FR-07. Pasa por la misma validación de ventana y duplicado; el cuestionario no aplica."""
    if not motivo or not motivo.strip():
        raise ErrorRegistro("Escribe el motivo del registro asistido.")
    alumno = buscar_alumno(no_control)
    if Registro.objects.filter(alumno=alumno, conferencia=conferencia).exists():
        raise ErrorRegistro(f"{alumno.nombre_completo} ya tiene un registro en esta conferencia.")
    ahora = timezone.now()
    valido, motivo_val = validacion.evaluar(conferencia, ahora, 0, 0, 0, False, aplica_cuestionario=False)
    registro = Registro.objects.create(
        alumno=alumno, conferencia=conferencia, minuto_qr=ahora, origen=Registro.ASISTIDO,
        motivo_asistido=motivo.strip(), registrado_por=usuario, valido=valido, motivo=motivo_val)
    Bitacora.registrar(usuario, "Registro asistido", registro.folio, f"{alumno.no_control}: {motivo}")
    return registro


# ---------------------------------------------------------------- CU-04
def enviar_validos(usuario, conferencia=None):
    """FR-10: envía a Servicios Escolares solo los registros válidos aún no enviados.
    Un segundo clic no duplica: si no hay nuevos, devuelve None."""
    with transaction.atomic():
        qs = Registro.objects.select_for_update().filter(valido=True, lote__isnull=True)
        if conferencia:
            qs = qs.filter(conferencia=conferencia)
        ids = list(qs.values_list("pk", flat=True))
        if not ids:
            return None
        hoy = timezone.localdate()
        n = Lote.objects.filter(enviado__date=hoy).count() + 1
        lote = Lote.objects.create(codigo=f"{hoy:%Y%m%d}-{n:02d}", enviado_por=usuario)
        Registro.objects.filter(pk__in=ids).update(lote=lote)
    Bitacora.registrar(usuario, "Envío a Servicios Escolares", lote, f"{len(ids)} registros válidos")
    return lote


# ---------------------------------------------------------------- CU-05
COLUMNAS_PADRON = ["no_control", "nombre", "apellidos", "carrera", "semestre", "grupo", "telefono", "correo"]


def _carrera(valor):
    v = (valor or "").strip()
    if v.upper() in CARRERAS_DICT:
        return v.upper()
    for clave, nombre in CARRERAS:
        if v.lower() in (nombre.lower(), nombre.lower().replace("ing. en ", "").replace("ing. ", "")
                         .replace("lic. en ", "")):
            return clave
    return None


def cargar_padron(archivo_texto, usuario=None):
    """FR-03. Devuelve {'aceptadas': n, 'rechazadas': [(fila, motivo), ...]} o lanza ErrorRegistro si faltan columnas."""
    lector = csv.DictReader(io.StringIO(archivo_texto.lstrip("﻿")))
    columnas = [c.strip().lower() for c in (lector.fieldnames or [])]
    faltan = [c for c in COLUMNAS_PADRON if c not in columnas]
    sobran = [c for c in columnas if c not in COLUMNAS_PADRON]
    if faltan or sobran:
        partes = []
        if faltan:
            partes.append("faltan las columnas: " + ", ".join(faltan))
        if sobran:
            partes.append("sobran las columnas: " + ", ".join(sobran))
        raise ErrorRegistro("El archivo no tiene el formato del padrón: " + "; ".join(partes) +
                            ". Usa la plantilla con las columnas " + ", ".join(COLUMNAS_PADRON) + ".")
    aceptadas, rechazadas = 0, []
    for i, fila in enumerate(lector, start=2):
        fila = {k.strip().lower(): (v or "").strip() for k, v in fila.items() if k}
        motivo = None
        carrera = _carrera(fila["carrera"])
        if not (fila["no_control"].isdigit() and len(fila["no_control"]) == 8):
            motivo = "número de control vacío o sin 8 dígitos"
        elif not fila["nombre"] or not fila["apellidos"]:
            motivo = "nombre o apellidos vacíos"
        elif not carrera:
            motivo = "carrera vacía o no reconocida"
        elif not fila["semestre"].isdigit():
            motivo = "semestre vacío o no numérico"
        elif not fila["grupo"]:
            motivo = "grupo vacío"
        elif fila["telefono"] and not (fila["telefono"].isdigit() and len(fila["telefono"]) == 10):
            motivo = "teléfono sin 10 dígitos"
        elif "@" not in fila["correo"]:
            motivo = "correo vacío o inválido"
        if motivo:
            rechazadas.append((i, motivo))
            continue
        Alumno.objects.update_or_create(no_control=fila["no_control"], defaults=dict(
            nombre=fila["nombre"], apellidos=fila["apellidos"], carrera=carrera,
            semestre=int(fila["semestre"]), grupo=fila["grupo"], telefono=fila["telefono"], correo=fila["correo"]))
        aceptadas += 1
    Bitacora.registrar(usuario, "Carga de padrón", f"{aceptadas} filas",
                       f"Rechazadas: {len(rechazadas)}")
    return {"aceptadas": aceptadas, "rechazadas": rechazadas}


# ---------------------------------------------------------------- CU-06
COLUMNAS_CSV = ["folio", "no_control", "nombre", "apellidos", "carrera", "semestre", "grupo", "correo",
                "telefono", "conferencia", "fecha_conferencia", "creditos_conferencia", "aciertos_pct",
                "cuestionario_valido", "origen", "conferencias_validas", "credito"]
OBLIGATORIAS = ["folio", "no_control", "nombre", "apellidos", "carrera", "semestre", "grupo", "correo",
                "conferencia", "fecha_conferencia"]


def filas_csv(lote):
    cfg = Configuracion.actual()
    filas = []
    regs = lote.registros.select_related("alumno", "conferencia").order_by("alumno__carrera", "alumno_id")
    for r in regs:
        a = r.alumno
        n_validas = validacion.conferencias_validas(a)
        filas.append(OrderedDict([
            ("folio", r.folio), ("no_control", a.no_control), ("nombre", a.nombre), ("apellidos", a.apellidos),
            ("carrera", a.get_carrera_display()), ("semestre", a.semestre), ("grupo", a.grupo),
            ("correo", a.correo), ("telefono", a.telefono), ("conferencia", r.conferencia.nombre),
            ("fecha_conferencia", f"{r.conferencia.fecha:%Y-%m-%d}"),
            ("creditos_conferencia", r.conferencia.creditos),
            ("aciertos_pct", r.porcentaje if r.origen != Registro.ASISTIDO else ""),
            ("cuestionario_valido", "SI" if r.valido else "NO"), ("origen", r.get_origen_display()),
            ("conferencias_validas", n_validas),
            ("credito", "SI" if n_validas >= cfg.conferencias_para_credito else "NO"),
        ]))
    return filas


def problemas_csv(filas):
    """NFR-09: lista (fila, columnas vacías) de las filas con columnas obligatorias vacías."""
    return [(i, [c for c in OBLIGATORIAS if f[c] in ("", None)])
            for i, f in enumerate(filas, start=2) if any(f[c] in ("", None) for c in OBLIGATORIAS)]


def generar_csv(lote, usuario=None):
    """Devuelve (contenido, problemas). Si hay problemas, no se debe descargar."""
    filas = filas_csv(lote)
    problemas = problemas_csv(filas)
    if problemas:
        return None, problemas
    salida = io.StringIO()
    w = csv.DictWriter(salida, fieldnames=COLUMNAS_CSV, lineterminator="\r\n")
    w.writeheader()
    w.writerows(filas)
    lote.exportaciones += 1
    lote.save(update_fields=["exportaciones"])
    Bitacora.registrar(usuario, "Exportación CSV para el SIIC", lote, f"{len(filas)} filas")
    # UTF-8 con BOM para que Excel muestre bien los acentos.
    return "﻿" + salida.getvalue(), []


# ---------------------------------------------------------------- CU-07
def _por_alumno(lote):
    grupos = OrderedDict()
    for r in lote.registros.select_related("alumno", "conferencia"):
        grupos.setdefault(r.alumno, []).append(r)
    return grupos


def confirmar_carga(lote, usuario):
    """FR-12 + FR-13/FR-14: marca el lote como cargado y avisa a cada alumno (RN-12)."""
    if lote.estado == Lote.CARGADO:
        raise ErrorRegistro("Este lote ya estaba confirmado como cargado. No se volvieron a enviar avisos.")
    lote.estado, lote.confirmado_por, lote.confirmado, lote.motivo_falla = Lote.CARGADO, usuario, timezone.now(), ""
    lote.save()
    Bitacora.registrar(usuario, "Carga confirmada en el SIIC", lote)
    cfg = Configuracion.actual()
    n = 0
    for alumno, regs in _por_alumno(lote).items():
        asunto, texto = notificaciones.msg_cargado(alumno, regs, validacion.tiene_credito(alumno, cfg))
        notificaciones.notificar(alumno, "cargado", asunto, texto)
        n += 1
    return n


def reportar_falla(lote, usuario, motivo):
    """FR-12 + FR-27 / RN-16."""
    if not motivo or not motivo.strip():
        raise ErrorRegistro("Escribe el motivo de la falla; se enviará a los alumnos afectados.")
    if lote.estado == Lote.CARGADO:
        raise ErrorRegistro("Este lote ya está confirmado como cargado.")
    lote.estado, lote.motivo_falla, lote.confirmado_por, lote.confirmado = Lote.FALLA, motivo.strip(), usuario, timezone.now()
    lote.save()
    Bitacora.registrar(usuario, "Falla en la carga del SIIC", lote, motivo)
    n = 0
    for alumno, regs in _por_alumno(lote).items():
        asunto, texto = notificaciones.msg_falla(alumno, regs, motivo.strip())
        notificaciones.notificar(alumno, "falla", asunto, texto)
        n += 1
    return n
