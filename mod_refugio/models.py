from django.db import models


class Refugio(models.Model):
    id_refugio = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=30)
    direccion = models.CharField(max_length=50)
    telefono = models.IntegerField()
    correo = models.CharField(max_length=50)
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        managed = False
        db_table = "refugio"


class Personal(models.Model):
    rut_personal = models.CharField(max_length=10, primary_key=True)
    rol = models.CharField(
        max_length=50,
        choices=[
            ("cuidador", "Cuidador"),
            ("administrativo", "Administrativo"),
            ("coordinador", "Coordinador"),
            ("veterinario", "Veterinario"),
        ],
    )
    fecha_ingreso = models.DateField()
    fecha_salida = models.DateField(null=True, blank=True)
    telefono_emergencia = models.IntegerField()
    direccion = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = "personal"


class Usuario(models.Model):
    id_usuario = models.BigAutoField(primary_key=True)
    p_nombre = models.CharField(max_length=50)
    s_nombre = models.CharField(max_length=50)
    ap_paterno = models.CharField(max_length=50)
    ap_materno = models.CharField(max_length=50)
    contrasena_hash = models.CharField(max_length=128)
    correo = models.CharField(max_length=50, null=True, blank=True)
    personal = models.ForeignKey(
        Personal,
        on_delete=models.DO_NOTHING,
        db_column="rut_personal",
        null=True,
        blank=True,
        related_name="usuarios",
    )
    genero = models.CharField(max_length=50)
    fecha_nacimiento = models.DateField()
    telefono = models.DecimalField(
        max_digits=1000,
        decimal_places=0,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "usuario"


class Raza(models.Model):
    id_raza = models.BigAutoField(primary_key=True)
    nomb_raza = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = "raza"


class Animal(models.Model):
    id_animal = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=20, null=True, blank=True)
    edad_aprox = models.SmallIntegerField()
    sexo = models.CharField(
        max_length=50,
        choices=[
            ("macho", "Macho"),
            ("hembra", "Hembra"),
            ("desconocido", "Desconocido"),
        ],
    )
    peso = models.DecimalField(max_digits=5, decimal_places=2)
    descripcion = models.TextField()
    lugar_rescate = models.CharField(max_length=50)
    condicion = models.CharField(
        max_length=50,
        choices=[
            ("sano", "Sano"),
            ("en_tratamiento", "En tratamiento"),
            ("grave", "Grave"),
        ],
    )
    especie = models.CharField(
        max_length=50,
        choices=[
            ("perro", "Perro"),
            ("gato", "Gato"),
            ("otro", "Otro"),
        ],
    )
    microchip = models.BooleanField(default=False)
    foto_url = models.TextField(null=True, blank=True)
    fecha_ingreso = models.DateField()
    fecha_salida = models.DateField(null=True, blank=True)
    comportamiento = models.CharField(max_length=50)
    raza = models.ForeignKey(
        Raza,
        on_delete=models.DO_NOTHING,
        db_column="id_raza",
        related_name="animales",
    )
    id_rescate = models.BigIntegerField()
    id_estado = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = "animal"
