from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django import forms
from django.core.paginator import Paginator
from django.template import Context
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from . import views
from .forms import ComentarioForm, PublicacionForm
from .models import Comentario, Publicacion, PublicacionPersonal


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
        publicaciones.annotate.return_value = publicaciones
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

    def test_publicaciones_se_paginan_de_cinco_en_cinco_y_ordenadas_por_recencia(self):
        request = RequestFactory().get("/foro/?page=2")

        pagina = views._pagina_publicaciones(request, list(range(23)))

        self.assertEqual(pagina.object_list, list(range(5, 10)))
        self.assertEqual(pagina.paginator.per_page, 5)
        self.assertEqual(
            Publicacion._meta.ordering,
            ("-fecha_publicacion", "-id_publicacion"),
        )

    def test_contador_muestra_el_total_de_publicaciones_en_ambas_vistas(self):
        context = {
            "publicaciones": [],
            "page_obj": Paginator(range(14), 5).get_page(1),
            "usuario_conectado": None,
            "publicacion_form": PublicacionForm(),
            "tipo_seleccionado": "",
            "tipos_publicacion": (),
        }

        for plantilla in ("publicaciones.html", "moderacion.html"):
            with self.subTest(plantilla=plantilla):
                html = get_template(plantilla).template.render(Context(context))
                self.assertRegex(
                    html,
                    r'<span class="badge rounded-pill bg-success">\s*14\s*</span>',
                )

    def test_vista_publica_filtra_publicaciones_y_comentarios_visibles(self):
        publicaciones = Mock()
        publicaciones.annotate.return_value = publicaciones
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
        publicaciones.annotate.assert_called_once()
        self.assertIsInstance(
            publicaciones.annotate.call_args.kwargs["es_publicacion_personal"],
            views.Exists,
        )

    def test_publicacion_de_personal_se_muestra_destacada(self):
        publicacion = SimpleNamespace(
            pk=12,
            titulo="Aviso del refugio",
            categoria="rescate",
            fecha_publicacion=date(2026, 11, 13),
            es_publicacion_personal=True,
            contenido="Información para la comunidad.",
            ubicacion="Santiago",
            comentarios=SimpleNamespace(all=lambda: []),
            id_estado=SimpleNamespace(nombre="Publicada"),
        )

        html = get_template("publicaciones.html").template.render(
            Context(
                {
                    "publicaciones": [publicacion],
                    "usuario_conectado": None,
                    "publicacion_form": PublicacionForm(),
                }
            )
        )

        self.assertIn("Publicación del personal", html)
        self.assertIn("border-success", html)

    def test_comentarios_se_despliegan_desde_el_tercero_en_ambas_vistas(self):
        usuario = SimpleNamespace(p_nombre="Ana", ap_paterno="Pérez")
        comentarios = [
            SimpleNamespace(
                pk=numero,
                id_usuario=usuario,
                id_estado=SimpleNamespace(nombre="Visible"),
                fecha=date(2026, 11, numero),
                contenido=f"Comentario {numero}",
            )
            for numero in range(1, 4)
        ]
        publicacion = SimpleNamespace(
            pk=12,
            titulo="Aviso del refugio",
            categoria="rescate",
            fecha_publicacion=date(2026, 11, 13),
            es_publicacion_personal=False,
            contenido="Información para la comunidad.",
            ubicacion="Santiago",
            comentarios=SimpleNamespace(all=lambda: comentarios),
            id_estado=SimpleNamespace(nombre="Publicada"),
        )
        context = {
            "publicaciones": [publicacion],
            "page_obj": Paginator([publicacion], 5).get_page(1),
            "usuario_conectado": None,
            "publicacion_form": PublicacionForm(),
            "tipos_publicacion": (),
            "tipo_seleccionado": "",
        }

        for plantilla in ("publicaciones.html", "moderacion.html"):
            with self.subTest(plantilla=plantilla):
                html = get_template(plantilla).template.render(Context(context))
                inicio_desplegable = html.index("<details")
                self.assertLess(html.index("Comentario 1"), inicio_desplegable)
                self.assertLess(html.index("Comentario 2"), inicio_desplegable)
                self.assertGreater(html.index("Comentario 3"), inicio_desplegable)
                self.assertIn("Mostrar todos los comentarios", html)

                context["publicaciones"][0].comentarios = SimpleNamespace(
                    all=lambda: comentarios[:2]
                )
                html_con_dos = get_template(plantilla).template.render(Context(context))
                self.assertNotIn("<details", html_con_dos)

                context["publicaciones"][0].comentarios = SimpleNamespace(
                    all=lambda: comentarios
                )

    def test_solo_personal_puede_abrir_moderacion(self):
        request = RequestFactory().get("/foro/moderacion/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        pagina = SimpleNamespace(object_list=[])

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views.Paginator") as paginador,
            patch("mod_foro.views.render", return_value=object()) as render,
        ):
            personal_filter.return_value.exists.return_value = True
            paginador.return_value.get_page.return_value = pagina
            response = views.moderacion(request)

        self.assertIs(response, render.return_value)
        personal_filter.assert_called_once_with(
            id_usuario__supabase_uid="staff-uuid",
        )
        paginador.assert_called_once()
        self.assertEqual(paginador.call_args.args[1], 5)
        paginador.return_value.get_page.assert_called_once_with(None)
        self.assertEqual(render.call_args.args[1], "moderacion.html")
        queryset = paginador.call_args.args[0]
        self.assertEqual(
            [condition.rhs for condition in queryset.query.where.children],
            ["Publicacion"],
        )
        prefetch = queryset._prefetch_related_lookups[0]
        self.assertEqual(
            [condition.rhs for condition in prefetch.queryset.query.where.children],
            ["Comentario"],
        )

    def test_moderacion_filtra_publicaciones_por_tipo(self):
        request = RequestFactory().get(
            "/foro/moderacion/",
            {"tipo": "rescate", "page": "2"},
        )
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        publicaciones = Mock()
        publicaciones.filter.return_value = publicaciones
        pagina = SimpleNamespace(object_list=[])

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch(
                "mod_foro.views.Publicacion.objects.filter",
                return_value=publicaciones,
            ) as filtrar_publicaciones,
            patch("mod_foro.views.Paginator") as paginador,
            patch("mod_foro.views.render") as render,
        ):
            personal_filter.return_value.exists.return_value = True
            paginador.return_value.get_page.return_value = pagina
            views.moderacion(request)

        filtrar_publicaciones.assert_called_once_with(
            id_estado__tipo_estado="Publicacion",
        )
        publicaciones.filter.assert_called_once_with(categoria="rescate")
        context = render.call_args.args[2]
        self.assertEqual(context["publicaciones"], [])
        self.assertEqual(context["tipo_seleccionado"], "rescate")
        self.assertEqual(paginador.call_args.args[1], 5)
        paginador.return_value.get_page.assert_called_once_with("2")
        self.assertEqual(
            context["tipos_publicacion"],
            (("adopcion", "Adopción"), ("rescate", "Rescate")),
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
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch(
                "mod_foro.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_foro.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = False
            response = views.crear_publicacion(request)

        self.assertEqual(response.status_code, 302)
        publicacion.save.assert_called_once_with()

    def test_publicacion_de_personal_se_marca_para_destacarla(self):
        request = RequestFactory().post("/foro/publicar/", {})
        usuario = object()
        publicacion = Mock(pk=12)
        estado_publicada = object()
        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = publicacion

        with (
            patch("mod_foro.views._usuario_de_sesion", return_value=usuario),
            patch("mod_foro.views.PublicacionForm", return_value=form),
            patch("mod_foro.views._estado_foro", return_value=estado_publicada),
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch(
                "mod_foro.views.PublicacionPersonal.objects.create"
            ) as crear_marca,
            patch(
                "mod_foro.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_foro.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.crear_publicacion(request)

        self.assertEqual(response.status_code, 302)
        publicacion.save.assert_called_once_with()
        personal_filter.assert_called_once_with(id_usuario=usuario)
        crear_marca.assert_called_once_with(
            publicacion=publicacion,
            usuario=usuario,
        )

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
        self.assertEqual(
            reverse(
                "mod_foro:eliminar_comentario",
                args=(34,),
            ),
            "/foro/comentarios/34/eliminar/",
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

    def test_ruta_eliminar_publicacion(self):
        self.assertEqual(
            reverse("mod_foro:eliminar_publicacion", args=(12,)),
            "/foro/publicaciones/12/eliminar/",
        )

    def test_personal_elimina_publicacion_y_sus_comentarios(self):
        request = RequestFactory().post("/foro/publicaciones/12/eliminar/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        publicacion = Mock()
        comentarios = Mock()
        eventos = Mock()
        eventos.attach_mock(comentarios.delete, "eliminar_comentarios")
        eventos.attach_mock(publicacion.delete, "eliminar_publicacion")

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch(
                "mod_foro.views.Publicacion.objects.select_for_update"
            ) as bloquear_publicaciones,
            patch(
                "mod_foro.views.PublicacionPersonal.objects.filter"
            ) as marcas,
            patch(
                "mod_foro.views.get_object_or_404",
                return_value=publicacion,
            ) as buscar,
            patch(
                "mod_foro.views.Comentario.objects.filter",
                return_value=comentarios,
            ) as buscar_comentarios,
            patch(
                "mod_foro.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_foro.views.messages.success") as success,
        ):
            personal_filter.return_value.exists.return_value = True
            eventos.attach_mock(
                marcas.return_value.delete,
                "eliminar_marca_personal",
            )
            response = views.eliminar_publicacion(request, 12)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("mod_foro:moderacion"))
        bloquear_publicaciones.assert_called_once_with()
        buscar.assert_called_once_with(
            bloquear_publicaciones.return_value,
            pk=12,
        )
        marcas.assert_called_once_with(publicacion=publicacion)
        buscar_comentarios.assert_called_once_with(publicacion=publicacion)
        self.assertEqual(
            eventos.mock_calls,
            [
                call.eliminar_marca_personal(),
                call.eliminar_comentarios(),
                call.eliminar_publicacion(),
            ],
        )
        success.assert_called_once()

    def test_usuario_que_no_es_personal_no_puede_eliminar_publicacion(self):
        request = RequestFactory().post("/foro/publicaciones/12/eliminar/")
        request.session = {"refugio_usuario": {"id": "usuario-uuid"}}

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views.get_object_or_404") as buscar,
            patch("mod_foro.views.Comentario.objects.filter") as comentarios,
        ):
            personal_filter.return_value.exists.return_value = False
            response = views.eliminar_publicacion(request, 12)

        self.assertEqual(response.status_code, 403)
        buscar.assert_not_called()
        comentarios.assert_not_called()

    def test_eliminar_publicacion_solo_acepta_post(self):
        response = self.client.get(
            reverse("mod_foro:eliminar_publicacion", args=(12,))
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

    def test_personal_puede_eliminar_comentario(self):
        request = RequestFactory().post("/foro/comentarios/34/eliminar/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        comentario = Mock(publicacion_id=12)

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views.Comentario.objects.select_for_update") as bloquear,
            patch("mod_foro.views.get_object_or_404", return_value=comentario) as buscar,
            patch("mod_foro.views.transaction.atomic", return_value=nullcontext()),
            patch("mod_foro.views.messages.success") as success,
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.eliminar_comentario(request, 34)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/foro/moderacion/#publicacion-12")
        buscar.assert_called_once_with(bloquear.return_value, pk=34)
        comentario.delete.assert_called_once_with()
        success.assert_called_once()

    def test_usuario_sin_personal_no_puede_eliminar_comentario(self):
        request = RequestFactory().post("/foro/comentarios/34/eliminar/")
        request.session = {"refugio_usuario": {"id": "user-uuid"}}

        with (
            patch("mod_foro.views.Personal.objects.filter") as personal_filter,
            patch("mod_foro.views.Comentario.objects.select_for_update") as bloquear,
        ):
            personal_filter.return_value.exists.return_value = False
            response = views.eliminar_comentario(request, 34)

        self.assertEqual(response.status_code, 403)
        bloquear.assert_not_called()

    def test_eliminar_comentario_solo_acepta_post(self):
        response = self.client.get(
            reverse("mod_foro:eliminar_comentario", args=(34,))
        )

        self.assertEqual(response.status_code, 405)

    def test_modelos_usan_las_tablas_existentes(self):
        self.assertEqual(Publicacion._meta.db_table, "publicacion")
        self.assertEqual(Comentario._meta.db_table, "comentario")
        self.assertFalse(Publicacion._meta.managed)
        self.assertFalse(Comentario._meta.managed)
