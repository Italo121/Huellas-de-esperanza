import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mod_foro", "0004_delete_autorpublicacion"),
        ("mod_refugio", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicacionPersonal",
            fields=[
                (
                    "publicacion",
                    models.OneToOneField(
                        db_column="id_publicacion",
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="marca_personal",
                        serialize=False,
                        to="mod_foro.publicacion",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="publicaciones_destacadas_foro",
                        to="mod_refugio.usuario",
                    ),
                ),
            ],
            options={
                "db_table": "publicacion_personal_foro",
            },
        ),
    ]
