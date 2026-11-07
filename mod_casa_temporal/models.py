from django.db import models

# Create your models here.

class CasaTemporal(models.Model):
    id_casa = models.BigAutoField(primary_key=True)
    poblacion = models.CharField(max_length=255)
    calle = models.CharField(max_length=255)
    num_casa = models.SmallIntegerField()
    cant_persona = models.SmallIntegerField()
    cant_habitacion = models.SmallIntegerField()
    patio = models.BooleanField()
    metro_c = models.SmallIntegerField()
    evidencia = models.TextField()
    observacion = models.CharField(max_length=255, null=True, blank=True)
    fecha_ingreso = models.DateField()
    id_usuario = models.ForeignKey(
        "mod_refugio.Usuario",
        on_delete=models.DO_NOTHING,
        db_column="id_usuario",
        related_name="casas_temporales",
    )
    id_estado = models.ForeignKey(
        "mod_refugio.Estado",
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="casas_temporales",
    )

    class Meta:
        managed = False
        db_table = "casa_temporal"


class HogarAnimal(models.Model):
    id_asignacion = models.BigAutoField(primary_key=True)
    fecha_ingreso = models.DateField()
    fecha_salida = models.DateField(null=True, blank=True)
    id_casa = models.ForeignKey(
        CasaTemporal,
        on_delete=models.DO_NOTHING,
        db_column="id_casa",
        related_name="asignaciones_animales",
    )
    id_animal = models.ForeignKey(
        "mod_refugio.Animal",
        on_delete=models.DO_NOTHING,
        db_column="id_animal",
        related_name="asignaciones_hogar_temporal",
    )

    class Meta:
        managed = False
        db_table = "hogar_animal"


class SolicitudHogarTemporal(models.Model):
    id_solicitud_hog = models.BigAutoField(primary_key=True)
    fecha_solicitud = models.DateField()
    motivo = models.CharField(max_length=255)
    observacion = models.CharField(max_length=255, null=True, blank=True)
    fecha_respuesta = models.DateField(null=True, blank=True)
    id_casa = models.ForeignKey(
        CasaTemporal,
        on_delete=models.DO_NOTHING,
        db_column="id_casa",
        related_name="solicitudes_hogar_temporal",
    )
    id_estado = models.ForeignKey(
        "mod_refugio.Estado",
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="solicitudes_hogar_temporal",
    )
    rut_personal = models.ForeignKey(
        "mod_refugio.Personal",
        on_delete=models.DO_NOTHING,
        db_column="rut_personal",
        null=True,
        blank=True,
        related_name="solicitudes_hogar_temporal_respondidas",
    )

    class Meta:
        managed = False
        db_table = "solicitud_hogar_temporal"
