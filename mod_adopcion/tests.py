from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.test import RequestFactory
from django.urls import resolve, reverse

from .forms import RespuestaSolicitudAdopcionForm, SolicitudAdopcionForm
from . import views
from .models import SolicitudAdopcion
from .views import solicitar_adopcion


class SolicitudAdopcionSchemaTests(SimpleTestCase):
    def test_model_maps_to_existing_database_columns(self):
        self.assertEqual(
            SolicitudAdopcion._meta.pk.column,
            "id_solicitud_ad",
        )
        self.assertEqual(
            SolicitudAdopcion._meta.get_field("id_estado").column,
            "id_estado",
        )
        self.assertEqual(
            SolicitudAdopcion._meta.get_field("motivo").max_length,
            50,
        )


class SolicitudAdopcionFormTests(SimpleTestCase):
    def test_motivo_is_required_and_whitespace_is_rejected(self):
        form = SolicitudAdopcionForm(
            {"motivo": "   ", "observacion": ""}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("motivo", form.errors)

    def test_motivo_is_trimmed(self):
        form = SolicitudAdopcionForm(
            {"motivo": "  Quiero darle un hogar  ", "observacion": ""}
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["motivo"], "Quiero darle un hogar")

    def test_staff_response_only_allows_approval_or_rejection(self):
        self.assertTrue(
            RespuestaSolicitudAdopcionForm(
                {"action": "aprobada", "respuesta": ""}
            ).is_valid()
        )
        self.assertTrue(
            RespuestaSolicitudAdopcionForm(
                {"action": "rechazada", "respuesta": ""}
            ).is_valid()
        )
        self.assertFalse(
            RespuestaSolicitudAdopcionForm(
                {"action": "pendiente", "respuesta": ""}
            ).is_valid()
        )


class SolicitudAdopcionUrlTests(SimpleTestCase):
    def test_submission_route_resolves_to_existing_view(self):
        path = reverse(
            "mod_adopcion:solicitar_adopcion",
            kwargs={"animal_id": 7},
        )

        self.assertEqual(path, "/adopcion/solicitar/7/")
        self.assertIs(resolve(path).func, solicitar_adopcion)


class SeguimientoAdopcionAccessTests(SimpleTestCase):
    def test_anonymous_user_is_redirected_from_follow_up_list(self):
        request = RequestFactory().get("/adopcion/seguimiento/")
        request.session = {}

        response = views.listar_seguimientos(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login_usuario"), response.url)

    def test_non_staff_cannot_access_follow_up_list(self):
        request = RequestFactory().get("/adopcion/seguimiento/")
        request.session = {"refugio_usuario": {"id": "public-user"}}

        with patch("mod_adopcion.views.Personal.objects.filter") as personal_filter:
            personal_filter.return_value.exists.return_value = False
            response = views.listar_seguimientos(request)

        self.assertEqual(response.status_code, 403)

    def test_non_staff_cannot_access_adoption_detail_or_post_follow_up(self):
        request = RequestFactory().get("/adopcion/seguimiento/2/")
        request.session = {"refugio_usuario": {"id": "public-user"}}
        post_request = RequestFactory().post(
            "/adopcion/seguimiento/agregar/2/",
            {"llamada": "on", "id_estado": "1"},
        )
        post_request.session = request.session

        with patch("mod_adopcion.views.Personal.objects.filter") as personal_filter:
            personal_filter.return_value.exists.return_value = False
            detail_response = views.detalle_adopcion(request, id_adopcion=2)
            post_response = views.agregar_seguimiento(
                post_request,
                id_adopcion=2,
            )

        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)

    def test_personal_can_access_follow_up_list(self):
        request = RequestFactory().get("/adopcion/seguimiento/")
        request.session = {"refugio_usuario": {"id": "staff-user"}}
        adopciones = [SimpleNamespace(id_adopcion=2)]

        with (
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch("mod_adopcion.views.Adopcion.objects.select_related") as queryset,
            patch(
                "mod_adopcion.views.render",
                return_value=HttpResponse("follow-ups"),
            ) as render_mock,
        ):
            personal_filter.return_value.exists.return_value = True
            queryset.return_value.only.return_value.all.return_value.order_by.return_value = (
                adopciones
            )
            response = views.listar_seguimientos(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_mock.call_args.args[2]["adopciones"],
            adopciones,
        )


class SolicitudAdopcionViewTests(SimpleTestCase):
    def test_animal_detail_only_enables_editing_for_personal(self):
        animal = SimpleNamespace(pk=7)
        request = RequestFactory().get("/adopcion/animales/7/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}

        with (
            patch("mod_adopcion.views.get_object_or_404", return_value=animal),
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch("mod_adopcion.views.SolicitudAdopcion.objects.filter") as request_filter,
            patch("mod_adopcion.views.render", return_value=HttpResponse("detail")) as render_mock,
        ):
            personal_filter.return_value.exists.return_value = True
            request_filter.return_value.first.return_value = None

            response = views.detalle_animal(request, id_animal=7)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(render_mock.call_args.args[2]["puede_editar"])

    def test_animal_detail_does_not_enable_editing_for_public_user(self):
        animal = SimpleNamespace(pk=7)
        request = RequestFactory().get("/adopcion/animales/7/")
        request.session = {"refugio_usuario": {"id": "public-uuid"}}

        with (
            patch("mod_adopcion.views.get_object_or_404", return_value=animal),
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch("mod_adopcion.views.SolicitudAdopcion.objects.filter") as request_filter,
            patch("mod_adopcion.views.render", return_value=HttpResponse("detail")) as render_mock,
        ):
            personal_filter.return_value.exists.return_value = False
            request_filter.return_value.first.return_value = None

            response = views.detalle_animal(request, id_animal=7)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(render_mock.call_args.args[2]["puede_editar"])

    def test_anonymous_user_is_redirected_from_own_requests(self):
        request = RequestFactory().get("/adopcion/mis-solicitudes/")
        request.session = {}

        response = views.mis_solicitudes(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login_usuario"), response.url)

    def test_user_sees_only_own_requests_and_their_status(self):
        request = RequestFactory().get("/adopcion/mis-solicitudes/")
        supabase_uid = "550e8400-e29b-41d4-a716-446655440000"
        request.session = {"refugio_usuario": {"id": supabase_uid}}
        request.user = AnonymousUser()
        solicitud = SimpleNamespace(
            id_solicitud_adopcion=14,
            id_animal=SimpleNamespace(nombre="Luna", especie="perro"),
            id_estado=SimpleNamespace(nombre="En Revisión"),
            fecha_solicitud=date(2026, 10, 20),
            fecha_respuesta=None,
            respuesta="",
        )

        with (
            patch("mod_adopcion.views.SolicitudAdopcion.objects.filter") as filter_mock,
            patch(
                "mod_refugio.context_processors.Personal.objects.filter"
            ) as personal_filter,
        ):
            filter_mock.return_value.select_related.return_value.order_by.return_value = [
                solicitud
            ]
            personal_filter.return_value.exists.return_value = False

            response = views.mis_solicitudes(request)

        self.assertEqual(response.status_code, 200)
        filter_mock.assert_called_once_with(
            id_usuario__supabase_uid=supabase_uid
        )
        self.assertContains(response, "Luna")
        self.assertContains(response, "En Revisión")
        self.assertContains(response, "El refugio está evaluando tu solicitud")

    def test_animal_detail_template_renders_catalog_and_submission_urls(self):
        request = RequestFactory().get("/adopcion/animales/7/")
        request.session = {}
        request.user = AnonymousUser()
        animal = SimpleNamespace(
            id_animal=7,
            especie="perro",
            nombre="Luna",
            foto_url="",
            raza=SimpleNamespace(nomb_raza="Mestiza"),
        )

        content = render_to_string(
            "detalle-animal.html",
            {"animal": animal},
            request=request,
        )

        self.assertIn('href="/adopcion/animales-adopcion/"', content)
        self.assertIn('action="/adopcion/solicitar/7/"', content)

    def test_existing_request_disables_resubmission_and_links_to_tracking(self):
        request = RequestFactory().get("/adopcion/animales/7/")
        request.session = {}
        request.user = AnonymousUser()
        animal = SimpleNamespace(
            id_animal=7,
            especie="perro",
            nombre="Luna",
            foto_url="",
            raza=SimpleNamespace(nomb_raza="Mestiza"),
        )
        solicitud = SimpleNamespace(
            id_estado=SimpleNamespace(nombre="Pendiente")
        )

        content = render_to_string(
            "detalle-animal.html",
            {"animal": animal, "solicitud_existente": solicitud},
            request=request,
        )

        self.assertIn("Solicitud pendiente", content)
        self.assertIn('href="/adopcion/mis-solicitudes/"', content)
        self.assertNotIn('data-bs-target="#modalAdopcion"', content)
        self.assertNotIn('id="modalAdopcion"', content)

    def test_adoption_catalog_renders_animal_detail_links(self):
        request = RequestFactory().get("/adopcion/animales-adopcion/")
        request.session = {}
        animal = SimpleNamespace(
            id_animal=7,
            especie="perro",
            nombre="Luna",
            foto_url="",
            raza=SimpleNamespace(nomb_raza="Mestiza"),
            edad_aprox=2,
            sexo="hembra",
            peso="10.00",
            condicion="sano",
            descripcion="Busca una familia.",
        )

        with (
            patch("mod_adopcion.views.Animal.objects.select_related") as animal_query,
            patch("mod_adopcion.views.Animal.objects.order_by") as species_query,
        ):
            animal_query.return_value.order_by.return_value = [animal]
            species_query.return_value.values_list.return_value.distinct.return_value = [
                "perro"
            ]

            response = views.animales_adopcion(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Luna")
        self.assertContains(response, 'href="/adopcion/animales/7/"')

    def test_request_submission_persists_pending_data(self):
        request = RequestFactory().post(
            "/adopcion/solicitar/7/",
            {
                "motivo": "  Quiero adoptar  ",
                "observacion": "Tengo experiencia",
            },
        )
        request.session = {"refugio_usuario": {"id": "user-uuid"}}
        animal = SimpleNamespace(pk=7)
        usuario = SimpleNamespace(pk=3)

        with (
            patch("mod_adopcion.views.get_object_or_404", return_value=animal),
            patch("mod_adopcion.views.Usuario.objects.get", return_value=usuario),
            patch("mod_adopcion.views.SolicitudAdopcion.objects.filter") as filter_mock,
            patch(
                "mod_adopcion.views.Animal.objects.select_for_update"
            ) as animal_lock,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
            patch(
                "mod_adopcion.views.SolicitudAdopcion.objects.create"
            ) as create_mock,
            patch(
                "mod_adopcion.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_adopcion.views.messages.success"),
        ):
            animal_lock.return_value.get.return_value = animal
            filter_mock.return_value.exists.return_value = False
            state = SimpleNamespace(pk=9)
            state_filter.return_value.order_by.return_value.first.return_value = state

            response = solicitar_adopcion(request, animal_id=7)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("mod_adopcion:detalle_animal", args=(7,)))
        create_mock.assert_called_once_with(
            id_animal=animal,
            id_usuario=usuario,
            motivo="Quiero adoptar",
            observacion="Tengo experiencia",
            id_estado=state,
            fecha_solicitud=views.timezone.localdate(),
        )
