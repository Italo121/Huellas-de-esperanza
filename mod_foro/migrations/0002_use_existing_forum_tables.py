import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mod_foro", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="Comentario"),
                migrations.DeleteModel(name="Publicacion"),
                migrations.CreateModel(
                    name="Publicacion",
                    fields=[
                        (
                            "id_publicacion",
                            models.BigAutoField(primary_key=True, serialize=False),
                        ),
                        ("categoria", models.CharField(max_length=30)),
                        ("titulo", models.CharField(max_length=30)),
                        ("contenido", models.TextField()),
                        ("ubicacion", models.CharField(max_length=150)),
                        (
                            "fecha_publicacion",
                            models.DateField(default=django.utils.timezone.localdate),
                        ),
                        (
                            "id_estado",
                            models.ForeignKey(
                                db_column="id_estado",
                                on_delete=django.db.models.deletion.DO_NOTHING,
                                related_name="publicaciones_foro",
                                to="mod_refugio.estado",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "publicacion",
                        "managed": False,
                        "ordering": ("-fecha_publicacion", "-id_publicacion"),
                    },
                ),
                migrations.CreateModel(
                    name="Comentario",
                    fields=[
                        (
                            "id_comentario",
                            models.BigAutoField(primary_key=True, serialize=False),
                        ),
                        ("contenido", models.TextField()),
                        (
                            "fecha",
                            models.DateField(default=django.utils.timezone.localdate),
                        ),
                        (
                            "id_usuario",
                            models.ForeignKey(
                                db_column="id_usuario",
                                on_delete=django.db.models.deletion.DO_NOTHING,
                                related_name="comentarios_foro",
                                to="mod_refugio.usuario",
                            ),
                        ),
                        (
                            "id_estado",
                            models.ForeignKey(
                                db_column="id_estado",
                                on_delete=django.db.models.deletion.DO_NOTHING,
                                related_name="comentarios_foro",
                                to="mod_refugio.estado",
                            ),
                        ),
                        (
                            "publicacion",
                            models.ForeignKey(
                                db_column="id_publicacion",
                                on_delete=django.db.models.deletion.DO_NOTHING,
                                related_name="comentarios",
                                to="mod_foro.publicacion",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "comentario",
                        "managed": False,
                        "ordering": ("fecha", "id_comentario"),
                    },
                ),
            ],
        ),
    ]
