from django.urls import path

from . import views

app_name = "mod_donacion"

urlpatterns = [
    path("", views.necesidades, name="necesidades"),
    path("necesidad/crear/", views.crear_necesidad, name="crear_necesidad"),
    path("gestion/", views.gestion_donaciones, name="gestion_donaciones"),
    path(
        "necesidad/<int:necesidad_id>/saciar/",
        views.marcar_necesidad_saciada,
        name="marcar_necesidad_saciada",
    ),
    path("crear/", views.crear_donacion, name="crear_donacion"),
]