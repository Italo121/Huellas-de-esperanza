from django.urls import path

from . import views

app_name = "mod_foro"

urlpatterns = [
    path("", views.publicaciones, name="publicaciones"),
    path("publicar/", views.crear_publicacion, name="crear_publicacion"),
    path(
        "publicaciones/<int:publicacion_id>/comentar/",
        views.crear_comentario,
        name="crear_comentario",
    ),
]
