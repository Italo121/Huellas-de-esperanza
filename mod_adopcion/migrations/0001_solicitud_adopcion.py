from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE solicitud_adopcion
                ADD COLUMN respuesta TEXT NOT NULL DEFAULT '',
                ADD COLUMN rut_personal_respuesta VARCHAR(10) NULL
                    REFERENCES personal(rut_personal) ON DELETE SET NULL
            """,
            reverse_sql="""
                ALTER TABLE solicitud_adopcion
                DROP COLUMN rut_personal_respuesta,
                DROP COLUMN respuesta
            """,
        ),
    ]
