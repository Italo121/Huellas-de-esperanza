
from django.urls import path
from . import views

urlpatterns = [
    path("", views.inicio, name="inicio_refugio"),
    path("animales/<int:animal_id>/editar/", views.editar_animal, name="editar_animal"),
    path("animales/<int:animal_id>/", views.ficha_animal, name="ficha_animal"),
    path("animales/registrar/", views.registro_animal, name="registro_animal"),
    path("login/", views.login_usuario, name="login_usuario"),
    path("registro/", views.registro_usuario, name="registro_usuario"),
    path("logout/", views.logout_usuario, name="logout_usuario"),
    path("login-personal/", views.login_personal, name="login_personal"),
]
