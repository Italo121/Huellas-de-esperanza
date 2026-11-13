from django.urls import path

from . import views

app_name = "mod_foro"

urlpatterns = [
    path("", views.publicaciones, name="publicaciones"),
    path("moderacion/", views.moderacion, name="moderacion"),
    path("publicar/", views.crear_publicacion, name="crear_publicacion"),
    path(
        "publicaciones/<int:publicacion_id>/comentar/",
        views.crear_comentario,
        name="crear_comentario",
    ),
    path(
        "publicaciones/<int:publicacion_id>/ocultar/",
        views.ocultar_publicacion,
        name="ocultar_publicacion",
    ),
    path(
        "publicaciones/<int:publicacion_id>/eliminar/",
        views.eliminar_publicacion,
        name="eliminar_publicacion",
    ),
    path(
        "comentarios/<int:comentario_id>/ocultar/",
        views.ocultar_comentario,
        name="ocultar_comentario",
    ),
    path(
        "comentarios/<int:comentario_id>/mostrar/",
        views.mostrar_comentario,
        name="mostrar_comentario",
    ),
]
