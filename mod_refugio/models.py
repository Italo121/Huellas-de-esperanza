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


class Veterinario(models.Model):
    rut_personal = models.OneToOneField(
        Personal,
        on_delete=models.DO_NOTHING,
        db_column="rut_personal",
        primary_key=True,
        related_name="datos_veterinario",
    )
    especialidad = models.TextField()
    experiencia = models.SmallIntegerField()

    class Meta:
        managed = False
        db_table = "veterinario"

    def __str__(self):
        return f"Veterinario {self.rut_personal_id}"


class EvaluacionAnimal(models.Model):
    ESTADOS_SALUD = [
        ("sano", "Sano"),
        ("en_tratamiento", "En tratamiento"),
        ("grave", "Grave"),
    ]

    id_evaluacion = models.BigAutoField(primary_key=True)
    fecha = models.DateField()
    estado_salud = models.TextField(choices=ESTADOS_SALUD)
    necesita_tratamiento = models.BooleanField()
    observacion = models.TextField()
    id_animal = models.ForeignKey(
        Animal,
        on_delete=models.DO_NOTHING,
        db_column="id_animal",
        related_name="evaluaciones_salud",
    )
    rut_personal = models.ForeignKey(
        Veterinario,
        on_delete=models.DO_NOTHING,
        db_column="rut_personal",
        related_name="evaluaciones",
    )

    class Meta:
        managed = False
        db_table = "evaluacion_animal"
        ordering = ("-fecha", "-id_evaluacion")

    def __str__(self):
        return f"Evaluación de {self.id_animal} ({self.fecha})"


class Vacuna(models.Model):
    id_vacuna = models.BigAutoField(primary_key=True)
    nomb_vacuna = models.TextField()
    descripcion = models.TextField()

    class Meta:
        managed = False
        db_table = "vacuna"
        ordering = ("nomb_vacuna",)

    def __str__(self):
        return self.nomb_vacuna


class VacunaAnimal(models.Model):
    id_vacuna_animal = models.BigAutoField(primary_key=True)
    fecha_aplicacion = models.DateField()
    fecha_prox_dosis = models.DateField(null=True, blank=True)
    aplicada = models.BooleanField()
    observacion = models.TextField()
    id_animal = models.ForeignKey(
        Animal,
        on_delete=models.DO_NOTHING,
        db_column="id_animal",
        related_name="vacunaciones",
    )
    id_vacuna = models.ForeignKey(
        Vacuna,
        on_delete=models.DO_NOTHING,
        db_column="id_vacuna",
        related_name="aplicaciones",
    )

    class Meta:
        managed = False
        db_table = "vacuna_animal"
        ordering = ("-fecha_aplicacion", "-id_vacuna_animal")

    def __str__(self):
        return f"{self.id_vacuna} - {self.id_animal}"


class Tratamiento(models.Model):
    TIPOS_TRATAMIENTO = [
        ("vacuna", "Vacuna"),
        ("cirugia", "Cirugía"),
        ("control", "Control"),
        ("desparasitacion", "Desparasitación"),
        ("otro", "Otro"),
    ]

    id_tratamiento = models.BigAutoField(primary_key=True)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField(null=True, blank=True)
    tipo_tratamiento = models.TextField(choices=TIPOS_TRATAMIENTO)
    detalle = models.TextField()
    observacion = models.TextField(null=True, blank=True)
    diagnostico = models.TextField()
    costo = models.IntegerField()
    id_estado = models.ForeignKey(
        Estado,
        on_delete=models.DO_NOTHING,
        db_column="id_estado",
        related_name="tratamientos",
    )
    rut_personal = models.ForeignKey(
        Veterinario,
        on_delete=models.DO_NOTHING,
        db_column="rut_personal",
        related_name="tratamientos",
    )
    id_animal = models.ForeignKey(
        Animal,
        on_delete=models.DO_NOTHING,
        db_column="id_animal",
        related_name="tratamientos",
    )

    class Meta:
        managed = False
        db_table = "tratamiento"
        ordering = ("-fecha_inicio", "-id_tratamiento")

    def __str__(self):
        return f"{self.tipo_tratamiento} - {self.id_animal}"
