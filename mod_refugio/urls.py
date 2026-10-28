
from django.urls import path
from . import views

urlpatterns = [
    path("", views.inicio, name="inicio_refugio"),
    path("login/", views.login_usuario, name="login_usuario"),
    path("registro/", views.registro_usuario, name="registro_usuario"),
    path("logout/", views.logout_usuario, name="logout_usuario"),
    path("login-personal/", views.login_personal, name="login_personal"),
]
