from django.urls import path
from mod_adopcion import views
from mod_adopcion.views import animales_adopcion

app_name = "mod_adopcion"

urlpatterns = [
    path('animales-adopcion/', animales_adopcion, name="animales_adopcion"),
    path("animales/<int:id_animal>/",views.detalle_animal,name="detalle_animal"),
    path(
        "seguimiento/",
        views.listar_seguimientos,
        name="seguimiento_adopciones"
    ),
     path(
        "seguimiento/<int:id_adopcion>/",
        views.detalle_adopcion,
        name="detalle_adopcion"
    ),
     path(
        "mis-adopciones/",
        views.mis_adopciones,
        name="mis_adopciones"
    ),
    path(
        "solicitar/<int:animal_id>/",
        views.solicitar_adopcion,
        name="solicitar_adopcion"
    ),
    path(
    "seguimiento/agregar/<int:id_adopcion>/",
    views.agregar_seguimiento,
    name="agregar_seguimiento"
    ),
]