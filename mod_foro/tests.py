from unittest.mock import Mock, patch

from django import forms
from django.test import SimpleTestCase
from django.urls import reverse

from .forms import ComentarioForm, PublicacionForm
from .models import Comentario, Publicacion


class ForoFormTests(SimpleTestCase):
    def test_publicacion_requiere_todos_los_campos_ingresados(self):
        form = PublicacionForm(
            data={"categoria": "", "titulo": "", "contenido": "", "ubicacion": ""}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("categoria", form.errors)
        self.assertIn("titulo", form.errors)
        self.assertIn("contenido", form.errors)
        self.assertIn("ubicacion", form.errors)

    def test_publicacion_acepta_datos_validos(self):
        form = PublicacionForm(
            data={
                "categoria": "adopcion",
                "titulo": "Una historia",
                "contenido": "Adopté a Luna.",
                "ubicacion": "Santiago",
            }
        )

        self.assertTrue(form.is_valid())

    def test_categoria_solo_acepta_opciones_en_minuscula(self):
        form = PublicacionForm(
            data={
                "categoria": "Adopcion",
                "titulo": "Una historia",
                "contenido": "Adopté a Luna.",
                "ubicacion": "Santiago",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("categoria", form.errors)

    def test_categoria_se_presenta_como_lista_de_opciones(self):
        form = PublicacionForm()

        self.assertIsInstance(form.fields["categoria"].widget, forms.Select)
        self.assertEqual(
            [value for value, _label in form.fields["categoria"].choices],
            ["", "adopcion", "rescate"],
        )

    def test_publicacion_muestra_errores_y_conserva_datos_en_formulario(self):
        publicaciones = Mock()
        publicaciones.prefetch_related.return_value.all.return_value = []

        with (
            patch("mod_foro.views._usuario_de_sesion", return_value=object()),
            patch(
                "mod_foro.views.Publicacion.objects.select_related",
                return_value=publicaciones,
            ),
        ):
            response = self.client.post(
                reverse("mod_foro:crear_publicacion"),
                {
                    "categoria": "",
                    "titulo": "Un título",
                    "contenido": "Un mensaje",
                    "ubicacion": "Santiago",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecciona una categoría.")
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="Un título"')

    def test_comentario_no_supera_1000_caracteres(self):
        form = ComentarioForm(data={"contenido": "x" * 1001})

        self.assertFalse(form.is_valid())
        self.assertIn("contenido", form.errors)

    def test_ruta_de_publicaciones(self):
        self.assertEqual(reverse("mod_foro:publicaciones"), "/foro/")

    def test_modelos_usan_las_tablas_existentes(self):
        self.assertEqual(Publicacion._meta.db_table, "publicacion")
        self.assertEqual(Comentario._meta.db_table, "comentario")
        self.assertFalse(Publicacion._meta.managed)
        self.assertFalse(Comentario._meta.managed)
