"""Límites de intentos (versión del salón, 24 nov 2026).

En una red compartida cualquiera puede llamar a la app. Estos límites frenan a quien prueba
contraseñas o NIP en masa: por dirección IP, con la caché de Django (en memoria, se borra al reiniciar).
"""
from functools import wraps

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.http import JsonResponse


def ip_de(request):
    # Detrás de un túnel o de PythonAnywhere la IP real llega en X-Forwarded-For. En la red del salón NO se usa:
    # cualquiera podría inventarse ese encabezado para saltarse el límite.
    if settings.CONFIAR_X_FORWARDED_FOR:
        reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if reenviada:
            return reenviada.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "") or "?"


def _clave(nombre, request):
    return f"limite:{nombre}:{ip_de(request)}"


def excedido(nombre, request, maximo):
    return cache.get(_clave(nombre, request), 0) >= maximo


def sumar(nombre, request, ventana_seg):
    clave = _clave(nombre, request)
    if cache.add(clave, 1, ventana_seg):
        return 1
    try:
        return cache.incr(clave)
    except ValueError:  # expiró justo ahora
        cache.set(clave, 1, ventana_seg)
        return 1


def limitar(nombre, maximo, ventana_seg):
    """Decorador para la API: más de `maximo` llamadas por IP en `ventana_seg` → 429."""
    def deco(vista):
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            if settings.LIMITES_ACTIVOS and sumar(nombre, request, ventana_seg) > maximo:
                return JsonResponse({"ok": False, "error": "Demasiados intentos desde este dispositivo. "
                                     "Espera unos minutos e inténtalo de nuevo."}, status=429)
            return vista(request, *args, **kwargs)
        return envuelta
    return deco


class LoginConLimite(auth_views.LoginView):
    """Inicio de sesión del personal: tras LOGIN_MAX_INTENTOS fallos por IP se bloquea LOGIN_BLOQUEO_MIN minutos."""

    template_name = "registro/login.html"

    def post(self, request, *args, **kwargs):
        if settings.LIMITES_ACTIVOS and excedido("login", request, settings.LOGIN_MAX_INTENTOS):
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form, bloqueado=settings.LOGIN_BLOQUEO_MIN))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        if settings.LIMITES_ACTIVOS:
            sumar("login", self.request, settings.LOGIN_BLOQUEO_MIN * 60)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(_clave("login", self.request))
        return super().form_valid(form)
