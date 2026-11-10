from django.db import models
from django.utils import timezone


class Publicacion(models.Model):
    id_publicacion = models.BigAutoField(primary_key=True)
    categoria = models.CharField(max_length=30)
    titulo = models.CharField(max_length=30)
    contenido = models.TextField()
    ubicacion = models.CharField(max_length=150)
    fecha_publicacion = models.DateField(default=timezone.localdate)
    id_estado = models.ForeignKey(
        "mod_refugio.Estado",
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="publicaciones_foro",
    )

    class Meta:
        managed = False
        db_table = "publicacion"
        ordering = ("-fecha_publicacion", "-id_publicacion")

    def __str__(self):
        return self.titulo


class Comentario(models.Model):
    id_comentario = models.BigAutoField(primary_key=True)
    contenido = models.TextField()
    fecha = models.DateField(default=timezone.localdate)
    id_usuario = models.ForeignKey(
        "mod_refugio.Usuario",
        on_delete=models.DO_NOTHING,
        db_column="id_usuario",
        related_name="comentarios_foro",
    )
    id_estado = models.ForeignKey(
        "mod_refugio.Estado",
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="comentarios_foro",
    )
    publicacion = models.ForeignKey(
        Publicacion,
        on_delete=models.DO_NOTHING,
        db_column="id_publicacion",
        related_name="comentarios",
    )

    class Meta:
        managed = False
        db_table = "comentario"
        ordering = ("fecha", "id_comentario")

    def __str__(self):
        return f"Comentario en {self.publicacion}"
