from django.conf import settings

GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS = "Comité Académico", "Profesor designado", "Servicios Escolares"


def roles_de(user):
    if not user.is_authenticated:
        return set()
    nombres = set(user.groups.values_list("name", flat=True))
    if user.is_superuser:
        nombres |= {GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS}
    return nombres


def roles(request):
    r = roles_de(request.user)
    return {
        "es_comite": GRUPO_COMITE in r,
        "es_profesor": GRUPO_PROFESOR in r,
        "es_servicios": GRUPO_SERVICIOS in r,
        "modo_local": settings.MODO_LOCAL,
        "notif_modo": settings.NOTIF_MODO,
    }
