from unittest.mock import Mock, patch

from django import forms
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from . import views
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
        publicaciones.select_related.return_value.prefetch_related.return_value.all.return_value = (
            []
        )

        with (
            patch("mod_foro.views._usuario_de_sesion", return_value=object()),
            patch(
                "mod_foro.views.Publicacion.objects.filter",
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
        self.assertNotContains(response, "Ocultar publicación")


    def test_comentario_no_supera_1000_caracteres(self):
        form = ComentarioForm(data={"contenido": "x" * 1001})

        self.assertFalse(form.is_valid())
        self.assertIn("contenido", form.errors)

    def test_ruta_de_publicaciones(self):
        self.assertEqual(reverse("mod_foro:publicaciones"), "/foro/")
        self.assertEqual(reverse("mod_foro:moderacion"), "/foro/moderacion/")

    def test_vista_publica_filtra_publicaciones_y_comentarios_visibles(self):
        publicaciones = Mock()
        publicaciones.select_related.return_value.prefetch_related.return_value.all.return_value = (
            []
        )

        with (
            patch(
                "mod_foro.views.Publicacion.objects.filter",
                return_value=publicaciones,
            ) as filtrar_publicaciones,
            patch("mod_foro.views._usuario_de_sesion", return_value=None),
            patch("mod_foro.views.render") as render,
        ):
            views._render_publicaciones(RequestFactory().get("/foro/"))

        filtrar_publicaciones.assert_called_once_with(
            id_estado__tipo_estado="Publicacion",
            id_estado__nombre="Publicada",
        )
        prefetch = publicaciones.select_related.return_value.prefetch_related.call_args.args[0]
        self.assertEqual(
            sorted(condition.rhs for condition in prefetch.queryset.query.where.children),
            ["Comentario", "Visible"],
        )

    def test_solo_personal_puede_abrir_moderacion(self):
        request = RequestFactory().get("/foro/moderacion/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views.render", return_value=object()) as render,
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.moderacion(request)

        self.assertIs(response, render.return_value)
        personal_filter.assert_called_once_with(
            id_usuario__supabase_uid="staff-uuid",
        )
        self.assertEqual(render.call_args.args[1], "moderacion.html")
        queryset = render.call_args.args[2]["publicaciones"]
        self.assertEqual(
            [condition.rhs for condition in queryset.query.where.children],
            ["Publicacion"],
        )
        prefetch = queryset._prefetch_related_lookups[0]
        self.assertEqual(
            [condition.rhs for condition in prefetch.queryset.query.where.children],
            ["Comentario"],
        )

    def test_usuario_sin_personal_no_puede_abrir_moderacion(self):
        request = RequestFactory().get("/foro/moderacion/")
        request.session = {"refugio_usuario": {"id": "user-uuid"}}

        with patch("mod_foro.views.Personal.objects.filter") as personal_filter:
            personal_filter.return_value.exists.return_value = False
            response = views.moderacion(request)

        self.assertEqual(response.status_code, 403)

    def test_usuario_sin_sesion_no_puede_abrir_moderacion(self):
        request = RequestFactory().get("/foro/moderacion/")
        request.session = {}

        with patch("mod_foro.views.messages.info"):
            response = views.moderacion(request)

        self.assertEqual(response.status_code, 302)

    def test_crear_publicacion_guarda_la_publicacion(self):
        request = RequestFactory().post("/foro/publicar/", {})
        usuario = object()
        publicacion = Mock()
        estado_publicada = object()
        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = publicacion

        with (
            patch("mod_foro.views._usuario_de_sesion", return_value=usuario),
            patch("mod_foro.views.PublicacionForm", return_value=form),
            patch("mod_foro.views._estado_foro", return_value=estado_publicada),
            patch("mod_foro.views.messages.success"),
        ):
            response = views.crear_publicacion(request)

        self.assertEqual(response.status_code, 302)
        publicacion.save.assert_called_once_with()

    def test_rutas_de_moderacion(self):
        self.assertEqual(
            reverse(
                "mod_foro:ocultar_publicacion",
                args=(12,),
            ),
            "/foro/publicaciones/12/ocultar/",
        )
        self.assertEqual(
            reverse(
                "mod_foro:ocultar_comentario",
                args=(34,),
            ),
            "/foro/comentarios/34/ocultar/",
        )
        self.assertEqual(
            reverse(
                "mod_foro:mostrar_comentario",
                args=(34,),
            ),
            "/foro/comentarios/34/mostrar/",
        )

    def test_personal_puede_ocultar_publicacion_cambiando_su_estado(self):
        request = RequestFactory().post("/foro/publicaciones/12/ocultar/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        publicacion = Mock()
        estado_oculta = object()

        with (
            patch("mod_foro.views._usuario_de_sesion", return_value=object()),
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views._estado_foro", return_value=estado_oculta) as estado,
            patch("mod_foro.views.get_object_or_404", return_value=publicacion) as buscar,
            patch("mod_foro.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.ocultar_publicacion(request, 12)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/foro/moderacion/#publicacion-12")
        self.assertIs(publicacion.id_estado, estado_oculta)
        publicacion.save.assert_called_once_with(update_fields=("id_estado",))
        estado.assert_called_once_with("Publicacion", "Archivada")
        buscar.assert_called_once_with(
            Publicacion,
            pk=12,
            id_estado__tipo_estado="Publicacion",
            id_estado__nombre="Publicada",
        )

    def test_ocultar_publicacion_solo_acepta_post(self):
        response = self.client.get(
            reverse("mod_foro:ocultar_publicacion", args=(12,))
        )

        self.assertEqual(response.status_code, 405)

    def test_usuario_que_no_es_personal_no_puede_ocultar_publicacion(self):
        request = RequestFactory().post("/foro/publicaciones/12/ocultar/")
        request.session = {"refugio_usuario": {"id": "usuario-uuid"}}

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views._estado_foro") as estado,
        ):
            personal_filter.return_value.exists.return_value = False
            response = views.ocultar_publicacion(request, 12)

        self.assertEqual(response.status_code, 403)
        estado.assert_not_called()

    def test_personal_puede_ocultar_cualquier_comentario(self):
        request = RequestFactory().post("/foro/comentarios/34/ocultar/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        comentario = Mock(publicacion_id=12)
        estado_oculto = object()

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views._estado_foro", return_value=estado_oculto) as estado,
            patch("mod_foro.views.get_object_or_404", return_value=comentario) as buscar,
            patch("mod_foro.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.ocultar_comentario(request, 34)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/foro/moderacion/#publicacion-12")
        self.assertIs(comentario.id_estado, estado_oculto)
        comentario.save.assert_called_once_with(update_fields=("id_estado",))
        estado.assert_called_once_with("Comentario", "Oculto (Moderado)")
        buscar.assert_called_once_with(
            Comentario,
            pk=34,
            id_estado__tipo_estado="Comentario",
            id_estado__nombre="Visible",
        )

    def test_personal_puede_volver_a_mostrar_comentario_oculto(self):
        request = RequestFactory().post("/foro/comentarios/34/mostrar/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        comentario = Mock(publicacion_id=12)
        estado_visible = object()

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views._estado_foro", return_value=estado_visible) as estado,
            patch("mod_foro.views.get_object_or_404", return_value=comentario) as buscar,
            patch("mod_foro.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.mostrar_comentario(request, 34)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/foro/moderacion/#publicacion-12")
        self.assertIs(comentario.id_estado, estado_visible)
        comentario.save.assert_called_once_with(update_fields=("id_estado",))
        estado.assert_called_once_with("Comentario", "Visible")
        buscar.assert_called_once_with(
            Comentario,
            pk=34,
            id_estado__tipo_estado="Comentario",
            id_estado__nombre="Oculto (Moderado)",
        )

    def test_volver_a_mostrar_comentario_solo_acepta_post(self):
        response = self.client.get(
            reverse("mod_foro:mostrar_comentario", args=(34,))
        )

        self.assertEqual(response.status_code, 405)

    def test_usuario_sin_personal_no_puede_volver_a_mostrar_comentario(self):
        request = RequestFactory().post("/foro/comentarios/34/mostrar/")
        request.session = {"refugio_usuario": {"id": "user-uuid"}}

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views._estado_foro") as estado,
            patch("mod_foro.views.get_object_or_404") as buscar,
        ):
            personal_filter.return_value.exists.return_value = False
            response = views.mostrar_comentario(request, 34)

        self.assertEqual(response.status_code, 403)
        estado.assert_not_called()
        buscar.assert_not_called()

    def test_usuario_sin_personal_no_puede_ocultar_comentario(self):
        request = RequestFactory().post("/foro/comentarios/34/ocultar/")
        request.session = {"refugio_usuario": {"id": "user-uuid"}}

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views._estado_foro", return_value=object()),
            patch("mod_foro.views.get_object_or_404") as buscar,
        ):
            personal_filter.return_value.exists.return_value = False
            response = views.ocultar_comentario(request, 34)

        self.assertEqual(response.status_code, 403)
        buscar.assert_not_called()

    def test_modelos_usan_las_tablas_existentes(self):
        self.assertEqual(Publicacion._meta.db_table, "publicacion")
        self.assertEqual(Comentario._meta.db_table, "comentario")
        self.assertFalse(Publicacion._meta.managed)
        self.assertFalse(Comentario._meta.managed)
