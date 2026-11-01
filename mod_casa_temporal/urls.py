from django.urls import path

from . import views

app_name = "mod_casa_temporal"

urlpatterns = [
    path(
        "mis-hogares/",
        views.mis_hogares_temporales,
        name="mis_hogares_temporales",
    ),
    path(
        "gestion-hogares/",
        views.gestion_hogares_temporales,
        name="gestion_hogares_temporales",
    ),
    path(
        "asignar-animal/",
        views.asignar_animal_hogar,
        name="asignar_animal_hogar",
    ),
    path(
        "hogares/",
        views.hogares_disponibles,
        name="hogares_disponibles",
    ),
    path(
        "solicitar/",
        views.solicitar_hogar_temporal,
        name="solicitar_hogar_temporal",
    ),
]
