
from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("", views.inicio, name="inicio_refugio"),
    path("informacion/", views.informacion_refugio, name="informacion_refugio"),
    path("refugio/",views.informacion_refugio,name="informacion_refugio_alias",),
    path("salud-animal/", views.gestion_salud_animal, name="gestion_salud_animal"),
    path("vacunas/", views.gestion_vacunas, name="gestion_vacunas"),
    path("animales/<int:animal_id>/editar/", views.editar_animal, name="editar_animal"),
    path("animales/<int:animal_id>/", views.ficha_animal, name="ficha_animal"),
    path("animales/registrar/", views.registro_animal, name="registro_animal"),
    path("login/", views.login_usuario, name="login_usuario"),
    path("registro/", views.registro_usuario, name="registro_usuario"),
    path("logout/", views.logout_usuario, name="logout_usuario"),
    path("login-personal/", views.login_personal, name="login_personal"),
]
