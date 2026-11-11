from django.urls import path

from . import views


app_name = "mod_estadistica_reporte"

urlpatterns = [
    path("", views.estadisticas, name="estadisticas"),
    path("personal/", views.personal, name="personal"),
    path("donaciones/", views.inventario_donaciones, name="inventario_donaciones"),
]
