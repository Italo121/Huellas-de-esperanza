from django.db import models
from django.utils import timezone


class Adopcion(models.Model):
    id_adopcion = models.BigAutoField(primary_key=True)
    id_animal = models.ForeignKey(
        "mod_refugio.Animal",
        on_delete=models.DO_NOTHING,
        db_column="id_animal",
        related_name="adopciones",
    )
    id_usuario = models.ForeignKey(
        "mod_refugio.Usuario",
        on_delete=models.DO_NOTHING,
        db_column="id_usuario",
        related_name="adopciones",
    )
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "adopcion"


class Estado(models.Model):
    id_estado = models.BigAutoField(primary_key=True)
    tipo_estado = models.CharField(max_length=50)
    nombre = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = "estado"


class SeguimientoAdopcion(models.Model):
    id_seg_adop = models.BigAutoField(primary_key=True)
    llamada = models.BooleanField()
    visita = models.BooleanField()
    anotacion = models.TextField(null=True, blank=True)
    evidencia = models.TextField(null=True, blank=True)
    fecha = models.DateTimeField()
    id_adopcion = models.ForeignKey(
        Adopcion,
        on_delete=models.DO_NOTHING,
        db_column="id_adopcion",
        related_name="seguimientos",
    )
    id_estado = models.ForeignKey(
        Estado,
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="seguimientos_adopcion",
    )

    class Meta:
        managed = False
        db_table = "seguimiento_adopcion"


class SolicitudAdopcion(models.Model):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (APROBADA, "Aprobada"),
        (RECHAZADA, "Rechazada"),
    ]

    id_solicitud_adopcion = models.BigAutoField(
        primary_key=True,
        db_column="id_solicitud_ad",
    )
    id_animal = models.ForeignKey(
        "mod_refugio.Animal",
        on_delete=models.PROTECT,
        db_column="id_animal",
        related_name="solicitudes_adopcion",
    )
    id_usuario = models.ForeignKey(
        "mod_refugio.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario",
        related_name="solicitudes_adopcion",
    )
    motivo = models.CharField(max_length=50)
    observacion = models.CharField(max_length=50, null=True, blank=True)
    id_estado = models.ForeignKey(
        Estado,
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="solicitudes_adopcion",
    )
    respuesta = models.TextField(blank=True)
    fecha_solicitud = models.DateField(default=timezone.localdate)
    fecha_respuesta = models.DateField(null=True, blank=True)
    respondida_por = models.ForeignKey(
        "mod_refugio.Personal",
        on_delete=models.SET_NULL,
        db_column="rut_personal_respuesta",
        null=True,
        blank=True,
        related_name="solicitudes_adopcion_respondidas",
    )

    class Meta:
        managed = False
        db_table = "solicitud_adopcion"
        ordering = ("-fecha_solicitud", "-id_solicitud_adopcion")
