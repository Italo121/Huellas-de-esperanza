from django.db import models


class Necesidad(models.Model):
    id_necesidad = models.BigAutoField(primary_key=True)
    tipo_necesidad = models.CharField(max_length=255)
    descripcion = models.CharField(max_length=255)
    saciada = models.BooleanField()
    fecha = models.DateField()
    fecha_cambio = models.DateField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "necesidad"

    def __str__(self):
        return f"{self.tipo_necesidad}: {self.descripcion}"


class Donacion(models.Model):
    id_donacion = models.BigAutoField(primary_key=True)
    tipo_donacion = models.CharField(max_length=255)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_donacion = models.DateField()
    descripcion = models.CharField(max_length=255)
    id_usuario = models.ForeignKey(
        "mod_refugio.Usuario",
        on_delete=models.DO_NOTHING,
        db_column="id_usuario",
        related_name="donaciones",
    )
    id_necesidad = models.ForeignKey(
        Necesidad,
        on_delete=models.DO_NOTHING,
        db_column="id_necesidad",
        null=True,
        blank=True,
        related_name="donaciones",
    )

    class Meta:
        managed = False
        db_table = "donacion"

    def __str__(self):
        return f"{self.tipo_donacion} - {self.cantidad}"
