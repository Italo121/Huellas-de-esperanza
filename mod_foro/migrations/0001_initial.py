import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("mod_refugio", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Publicacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=150)),
                ("contenido", models.TextField()),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "autor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="publicaciones_foro",
                        to="mod_refugio.usuario",
                    ),
                ),
            ],
            options={
                "verbose_name": "publicación",
                "verbose_name_plural": "publicaciones",
                "ordering": ("-fecha_creacion", "-id"),
            },
        ),
        migrations.CreateModel(
            name="Comentario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("contenido", models.TextField(max_length=1000)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "autor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="comentarios_foro",
                        to="mod_refugio.usuario",
                    ),
                ),
                (
                    "publicacion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comentarios",
                        to="mod_foro.publicacion",
                    ),
                ),
            ],
            options={
                "verbose_name": "comentario",
                "verbose_name_plural": "comentarios",
                "ordering": ("fecha_creacion", "id"),
            },
        ),
    ]
