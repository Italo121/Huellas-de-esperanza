from django.db import models

class Estado(models.Model):
    id_estado = models.BigAutoField(primary_key=True)
    tipo_estado = models.CharField(max_length=50)
    nombre = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = "estado"

    def __str__(self):
        return f"{self.tipo_estado} - {self.nombre}"


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


class Usuario(models.Model):
    id_usuario = models.BigAutoField(primary_key=True)
    p_nombre = models.CharField(max_length=50)
    s_nombre = models.CharField(max_length=50)
    ap_paterno = models.CharField(max_length=50)
    ap_materno = models.CharField(max_length=50)
    correo = models.EmailField(max_length=50, unique=True, null=True)
    genero = models.CharField(max_length=50)
    fecha_nacimiento = models.DateField()
    telefono = models.DecimalField(max_digits=20, decimal_places=0, null=True)
    supabase_uid = models.UUIDField(unique=True, null=True, editable=False)

    class Meta:
        db_table = 'usuario'

class Personal(models.Model):
    ROLES = [
        ('cuidador', 'Cuidador'),
        ('administrativo', 'Administrativo'),
        ('coordinador', 'Coordinador'),
        ('veterinario', 'Veterinario'),
    ]
    rut_personal = models.CharField(max_length=10, primary_key=True)
    rol = models.CharField(max_length=50, choices=ROLES)
    fecha_ingreso = models.DateField()
    fecha_salida = models.DateField(null=True, blank=True)
    telefono_emergencia = models.IntegerField()
    direccion = models.CharField(max_length=100)
    id_usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        db_column='id_usuario',
        null=True)
    id_estado = models.OneToOneField(
        Estado,
        on_delete=models.CASCADE,
        db_column='id_estado',
        null=True,
    )
    class Meta:
        db_table = 'personal'

class Rescate(models.Model):
    CONDICIONES = [
        ("sano", "Sano"),
        ("en_tratamiento", "En tratamiento"),
        ("grave", "Grave"),
    ]

    id_rescate = models.BigAutoField(primary_key=True)
    fecha_rescate = models.DateField()
    lugar_rescate = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=100)
    condicion_inicial = models.CharField(max_length=50, choices=CONDICIONES)
    observacion = models.CharField(max_length=50, null=True, blank=True)
    id_estado = models.ForeignKey(
        Estado,
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
    )
    rut_personal = models.ForeignKey(
        Personal,
        on_delete=models.DO_NOTHING,
        db_column="rut_personal",
    )

    class Meta:
        managed = False
        db_table = "rescate"


class Raza(models.Model):
    id_raza = models.BigAutoField(primary_key=True)
    nomb_raza = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = "raza"

    def __str__(self):
        return self.nomb_raza


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
