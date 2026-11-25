from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from registro import api, views
from registro.seguridad import LoginConLimite

urlpatterns = [
    path("", views.portada, name="portada"),
    path("app/", views.app_alumno, name="app_alumno"),
    path("acerca/", views.acerca, name="acerca"),
    path("sw.js", views.service_worker, name="sw"),
    path("manifest.webmanifest", views.manifest, name="manifest"),

    # API REST (E3 §3.5)
    path("api/conferencias/activas", api.conferencias_activas),
    path("api/paquete/<int:pk>", api.paquete),
    path("api/identificar", api.identificar),
    path("api/registros", api.registros),
    path("api/estado/codigo", api.pedir_codigo),
    path("api/estado", api.estado),

    # Sesión
    path("login/", LoginConLimite.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("inicio/", views.inicio, name="inicio"),

    # Profesor designado (P1)
    path("profesor/", views.profesor, name="profesor"),
    path("profesor/<int:pk>/", views.profesor_panel, name="profesor_panel"),
    path("profesor/<int:pk>/estado", views.profesor_estado, name="profesor_estado"),
    path("profesor/<int:pk>/asistido", views.profesor_asistido, name="profesor_asistido"),
    path("profesor/<int:pk>/sincronizar", views.profesor_sincronizar, name="profesor_sincronizar"),

    # Comité Académico (C1, C2, C3)
    path("comite/", views.comite, name="comite"),
    path("comite/tablero/", views.tablero, name="tablero"),
    path("comite/tablero/<str:carrera>/", views.detalle_carrera, name="detalle_carrera"),
    path("comite/enviar", views.enviar, name="enviar"),

    # Servicios Escolares (S1)
    path("servicios/", views.servicios_inicio, name="servicios"),
    path("servicios/lote/<int:pk>/", views.lote_detalle, name="lote_detalle"),
    path("servicios/lote/<int:pk>/csv", views.lote_csv, name="lote_csv"),
    path("servicios/lote/<int:pk>/confirmar", views.lote_confirmar, name="lote_confirmar"),
    path("servicios/lote/<int:pk>/falla", views.lote_falla, name="lote_falla"),
    path("avisos/", views.avisos, name="avisos"),
    path("bitacora/", views.bitacora, name="bitacora"),

    path("admin/", admin.site.urls),
]

admin.site.site_header = "TecNM Matehuala · Administración del registro de créditos"
admin.site.site_title = "TecNM Matehuala"
