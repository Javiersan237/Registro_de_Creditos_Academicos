"""Motor de validación (FR-25, E3 §2.6) y acreditación (FR-26, RN-13).

Evalúa cuatro condiciones en orden y reporta el primer motivo que falle:
  1. Dentro de la ventana de tiempo (RN-11)
  2. Primer registro del alumno en esa conferencia (RN-09)
  3. Tiempo mínimo de respuesta (RN-15)
  4. 50 % o más de aciertos (RN-14)
"""
from .models import Configuracion, Registro

MOTIVO_VENTANA = "Fuera de la ventana de tiempo"
MOTIVO_DUPLICADO = "Ya había un registro en esa conferencia"
MOTIVO_RAPIDO = "Respondió demasiado rápido"
MOTIVO_PUNTAJE = "Menos del porcentaje mínimo de aciertos"


def tiempo_minimo(total_preguntas, cfg):
    """RN-15: 20 s por pregunta, pero el mínimo exigido nunca pasa de 5 minutos."""
    return min(cfg.segundos_por_pregunta * total_preguntas, cfg.tiempo_minimo_tope_seg)


def evaluar(conferencia, minuto_qr, tiempo_seg, aciertos, total, duplicado, cfg=None, aplica_cuestionario=True):
    """Función pura (sin escribir en la base). Devuelve (valido, motivo)."""
    cfg = cfg or Configuracion.actual()
    if minuto_qr is None or not (conferencia.inicio_dt() <= minuto_qr <= conferencia.cierre_dt(cfg)):
        return False, MOTIVO_VENTANA
    if duplicado:
        return False, MOTIVO_DUPLICADO
    if aplica_cuestionario:
        if tiempo_seg < tiempo_minimo(total, cfg):
            return False, MOTIVO_RAPIDO
        porcentaje = (aciertos / total * 100) if total else 0
        if porcentaje < cfg.porcentaje_minimo:
            return False, MOTIVO_PUNTAJE
    return True, ""


def calificar(conferencia, respuestas):
    """Cuenta aciertos. respuestas = lista de índices elegidos, en el orden de las preguntas."""
    preguntas = list(conferencia.preguntas.all())
    aciertos = sum(1 for p, r in zip(preguntas, respuestas) if r is not None and int(r) == p.correcta)
    return aciertos, len(preguntas)


def conferencias_validas(alumno):
    return Registro.objects.filter(alumno=alumno, valido=True).count()


def tiene_credito(alumno, cfg=None):
    """FR-26: crédito con 2 o más conferencias válidas; las demás son evidencia adicional."""
    cfg = cfg or Configuracion.actual()
    return conferencias_validas(alumno) >= cfg.conferencias_para_credito
