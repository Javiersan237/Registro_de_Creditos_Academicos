from django.contrib import admin

from .models import Alumno, Aviso, Bitacora, Configuracion, Conferencia, Lote, Pregunta, Registro


@admin.register(Configuracion)
class ConfiguracionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "tolerancia_min", "porcentaje_minimo", "segundos_por_pregunta",
                    "conferencias_para_credito"]

    def has_add_permission(self, request):
        return not Configuracion.objects.exists()


@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ["no_control", "nombre", "apellidos", "carrera", "semestre", "grupo", "correo", "telefono"]
    list_filter = ["carrera", "semestre"]
    search_fields = ["no_control", "nombre", "apellidos", "correo"]


class PreguntaInline(admin.TabularInline):
    model = Pregunta
    extra = 0


@admin.register(Conferencia)
class ConferenciaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "fecha", "hora_inicio", "hora_fin", "creditos", "profesor"]
    inlines = [PreguntaInline]


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
    list_display = ["folio", "alumno", "conferencia", "porcentaje", "tiempo_seg", "origen", "valido", "motivo", "lote"]
    list_filter = ["valido", "origen", "conferencia", "alumno__carrera"]
    search_fields = ["folio", "alumno__no_control"]


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ["codigo", "enviado", "enviado_por", "estado", "confirmado"]


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ["creado", "alumno", "canal", "tipo", "destino", "estado", "error"]
    list_filter = ["canal", "estado", "tipo"]


@admin.register(Bitacora)
class BitacoraAdmin(admin.ModelAdmin):
    list_display = ["fecha", "usuario", "accion", "objeto", "detalle"]
    list_filter = ["accion"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
