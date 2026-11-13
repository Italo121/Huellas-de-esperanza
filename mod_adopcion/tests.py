from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.db import models
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.test import RequestFactory
from django.urls import resolve, reverse

from .forms import (
    RespuestaSolicitudAdopcionForm,
    SolicitudAdopcionForm,
    SolicitudDevolucionAdopcionForm,
)
from . import views
from .models import DevolucionAdopcion, SolicitudAdopcion
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
        self.assertIsInstance(
            SolicitudAdopcion._meta.get_field("motivo"),
            models.TextField,
        )

    def test_return_request_model_maps_to_existing_table(self):
        self.assertEqual(DevolucionAdopcion._meta.db_table, "devolucion_adopcion")
        self.assertEqual(DevolucionAdopcion._meta.pk.column, "id_dev")
        self.assertEqual(
            DevolucionAdopcion._meta.get_field("fecha_devolucion").column,
            "fecha_devolucion",
        )
        self.assertEqual(
            DevolucionAdopcion._meta.get_field("id_adopcion").column,
            "id_adopcion",
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

    def test_motivo_accepts_150_characters_and_rejects_more(self):
        long_motivo = "a" * 150
        form = SolicitudAdopcionForm({"motivo": long_motivo, "observacion": ""})

        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data["motivo"]), 150)
        self.assertFalse(
            SolicitudAdopcionForm(
                {"motivo": long_motivo + "a", "observacion": ""}
            ).is_valid()
        )
        self.assertEqual(
            SolicitudAdopcionForm.base_fields["motivo"].widget.attrs["maxlength"],
            "150",
        )

    def test_return_request_requires_reason_and_valid_animal_condition(self):
        form = SolicitudDevolucionAdopcionForm(
            {
                "motivo": "   ",
                "condicion_animal": "desconocido",
                "observacion": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("motivo", form.errors)
        self.assertIn("condicion_animal", form.errors)

    def test_return_request_cleans_fields(self):
        form = SolicitudDevolucionAdopcionForm(
            {
                "motivo": " No puedo seguir cuidándolo ",
                "condicion_animal": "sano",
                "observacion": "   ",
                "requiere_tratamiento": "on",
            }
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["motivo"], "No puedo seguir cuidándolo")
        self.assertEqual(form.cleaned_data["observacion"], "")
        self.assertTrue(form.cleaned_data["requiere_tratamiento"])

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

    def test_return_route_resolves_to_request_view(self):
        path = reverse(
            "mod_adopcion:solicitar_devolucion",
            kwargs={"id_adopcion": 7},
        )

        self.assertEqual(path, "/adopcion/mis-adopciones/7/devolver/")
        self.assertIs(resolve(path).func, views.solicitar_devolucion)


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
    def test_my_adoptions_includes_return_request_outcome(self):
        request = RequestFactory().get("/adopcion/mis-adopciones/")
        request.session = {"refugio_usuario": {"id": "user-uuid"}}
        adopcion = SimpleNamespace(id_adopcion=7)

        with (
            patch("mod_adopcion.views.Adopcion.objects.filter") as adoption_filter,
            patch(
                "mod_adopcion.views.DevolucionAdopcion.objects.filter"
            ) as return_filter,
            patch(
                "mod_adopcion.views.render",
                return_value=HttpResponse("adoptions"),
            ) as render_mock,
        ):
            adoption_filter.return_value.select_related.return_value.order_by.return_value = [
                adopcion
            ]
            return_filter.return_value.values_list.return_value = [
                (7, "Aprobada"),
                (8, "Rechazada"),
                (9, "Registrada"),
            ]

            response = views.mis_adopciones(request)

        self.assertEqual(response.status_code, 200)
        context = render_mock.call_args.args[2]
        self.assertEqual(context["devoluciones_solicitadas"], {7, 8, 9})
        self.assertEqual(context["devoluciones_aprobadas"], {7})
        self.assertEqual(context["devoluciones_rechazadas"], {8})
        return_filter.assert_called_once_with(id_adopcion_id__in=[7])

    def test_my_adoptions_renders_return_request_form_for_active_adoption(self):
        request = RequestFactory().get("/adopcion/mis-adopciones/")
        request.session = {}
        request.user = AnonymousUser()
        adopcion = SimpleNamespace(
            id_adopcion=7,
            fecha_inicio=date(2026, 1, 1),
            fecha_termino=None,
            id_animal=SimpleNamespace(
                nombre="Luna",
                especie="perro",
                foto_url="",
            ),
        )

        content = render_to_string(
            "mis-adopciones.html",
            {
                "adopciones": [adopcion],
                "devoluciones_solicitadas": set(),
                "devoluciones_aprobadas": set(),
                "devoluciones_rechazadas": set(),
            },
            request=request,
        )

        self.assertIn('data-bs-target="#devolucionModal7"', content)
        self.assertIn('action="/adopcion/mis-adopciones/7/devolver/"', content)
        self.assertIn('name="condicion_animal"', content)
        self.assertIn('name="requiere_tratamiento"', content)
        self.assertIn('name="csrfmiddlewaretoken"', content)
        self.assertIn("La adopción seguirá activa", content)

    def test_existing_return_request_hides_request_button(self):
        request = RequestFactory().get("/adopcion/mis-adopciones/")
        request.session = {}
        request.user = AnonymousUser()
        adopcion = SimpleNamespace(
            id_adopcion=7,
            fecha_inicio=date(2026, 1, 1),
            fecha_termino=None,
            id_animal=SimpleNamespace(
                nombre="Luna",
                especie="perro",
                foto_url="",
            ),
        )

        content = render_to_string(
            "mis-adopciones.html",
            {
                "adopciones": [adopcion],
                "devoluciones_solicitadas": {7},
                "devoluciones_aprobadas": set(),
                "devoluciones_rechazadas": set(),
            },
            request=request,
        )

        self.assertNotIn('data-bs-target="#devolucionModal7"', content)
        self.assertIn("Solicitud de devolución en revisión", content)

    def test_approved_return_is_shown_as_completed_adoption(self):
        request = RequestFactory().get("/adopcion/mis-adopciones/")
        request.session = {}
        request.user = AnonymousUser()
        adopcion = SimpleNamespace(
            id_adopcion=7,
            fecha_inicio=date(2026, 1, 1),
            fecha_termino=date(2026, 10, 30),
            id_animal=SimpleNamespace(
                nombre="Luna",
                especie="perro",
                foto_url="",
            ),
        )

        content = render_to_string(
            "mis-adopciones.html",
            {
                "adopciones": [adopcion],
                "devoluciones_solicitadas": {7},
                "devoluciones_aprobadas": {7},
                "devoluciones_rechazadas": set(),
            },
            request=request,
        )

        self.assertIn("Devolución aprobada", content)
        self.assertIn(
            "El animal fue devuelto al refugio y esta adopción finalizó.",
            content,
        )
        self.assertIn("30/10/2026", content)
        self.assertNotIn("Adopción registrada", content)
        self.assertNotIn('data-bs-target="#devolucionModal7"', content)

    def test_return_request_requires_login(self):
        request = RequestFactory().post("/adopcion/mis-adopciones/7/devolver/")
        request.session = {}

        response = views.solicitar_devolucion(request, id_adopcion=7)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login_usuario"), response.url)

    def test_return_request_rejects_get_requests(self):
        request = RequestFactory().get("/adopcion/mis-adopciones/7/devolver/")

        response = views.solicitar_devolucion(request, id_adopcion=7)

        self.assertEqual(response.status_code, 405)

    def test_return_request_creates_record_without_ending_adoption(self):
        request = RequestFactory().post(
            "/adopcion/mis-adopciones/7/devolver/",
            {
                "motivo": "No puedo seguir cuidándolo",
                "condicion_animal": "sano",
                "observacion": "Se encuentra bien",
                "requiere_tratamiento": "on",
            },
        )
        request.session = {"refugio_usuario": {"id": "user-uuid"}}
        adopcion = SimpleNamespace(
            id_adopcion=7,
            id_animal_id=3,
            fecha_termino=None,
            save=Mock(),
        )
        state = SimpleNamespace(pk=11)

        with (
            patch("mod_adopcion.views.Adopcion.objects.select_for_update") as lock_adoption,
            patch(
                "mod_adopcion.views.get_object_or_404",
                return_value=adopcion,
            ) as adoption_lookup,
            patch("mod_adopcion.views.DevolucionAdopcion.objects.filter") as return_filter,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
            patch("mod_adopcion.views.DevolucionAdopcion.objects.create") as create_mock,
            patch("mod_adopcion.views.transaction.atomic", return_value=nullcontext()),
            patch("mod_adopcion.views.messages.success") as success_mock,
            patch("mod_adopcion.views.messages.error") as error_mock,
        ):
            return_filter.return_value.exists.return_value = False
            state_filter.return_value.order_by.return_value.first.return_value = state

            response = views.solicitar_devolucion(request, id_adopcion=7)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("mod_adopcion:mis_solicitudes"))
        error_mock.assert_not_called()
        success_mock.assert_called_once()
        self.assertEqual(lock_adoption.call_count, 1)
        self.assertEqual(
            adoption_lookup.call_args.kwargs,
            {
                "id_adopcion": 7,
                "id_usuario__supabase_uid": "user-uuid",
                "fecha_termino__isnull": True,
            },
        )
        state_filter.assert_called_once_with(
            tipo_estado="Devolucion",
            nombre="Registrada",
        )
        create_mock.assert_called_once_with(
            fecha_devolucion=views.timezone.localdate(),
            motivo="No puedo seguir cuidándolo",
            condicion_animal="sano",
            observacion="Se encuentra bien",
            requiere_tratamiento=True,
            fecha_evaluacion=None,
            id_adopcion=adopcion,
            id_estado=state,
        )
        self.assertIsNone(adopcion.fecha_termino)
        adopcion.save.assert_not_called()

    def test_return_request_cannot_be_submitted_twice(self):
        request = RequestFactory().post(
            "/adopcion/mis-adopciones/7/devolver/",
            {
                "motivo": "No puedo seguir cuidándolo",
                "condicion_animal": "sano",
            },
        )
        request.session = {"refugio_usuario": {"id": "user-uuid"}}
        adopcion = SimpleNamespace(id_adopcion=7, fecha_termino=None)

        with (
            patch("mod_adopcion.views.get_object_or_404", return_value=adopcion),
            patch(
                "mod_adopcion.views.DevolucionAdopcion.objects.filter"
            ) as return_filter,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
            patch("mod_adopcion.views.DevolucionAdopcion.objects.create") as create_mock,
            patch("mod_adopcion.views.transaction.atomic", return_value=nullcontext()),
            patch("mod_adopcion.views.messages.info") as info_mock,
        ):
            return_filter.return_value.exists.return_value = True

            response = views.solicitar_devolucion(request, id_adopcion=7)

        self.assertEqual(response.status_code, 302)
        state_filter.assert_not_called()
        create_mock.assert_not_called()
        info_mock.assert_called_once()

    def test_animal_detail_only_enables_editing_for_personal(self):
        animal = SimpleNamespace(pk=7, id_estado=21, id_rescate=14)
        vacuna = SimpleNamespace(nomb_vacuna="Antirrábica")
        vacunas_animal = [SimpleNamespace(id_vacuna=vacuna)]
        usuario = SimpleNamespace(
            p_nombre="Ana",
            s_nombre="María",
            ap_paterno="Pérez",
            ap_materno="López",
        )
        rescate = SimpleNamespace(
            rut_personal=SimpleNamespace(id_usuario=usuario),
        )
        request = RequestFactory().get("/adopcion/animales/7/")
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}

        with (
            patch("mod_adopcion.views.get_object_or_404", return_value=animal),
            patch("mod_adopcion.views.Rescate.objects.select_related") as rescue_query,
            patch(
                "mod_adopcion.views.VacunaAnimal.objects.select_related"
            ) as vaccine_query,
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch("mod_adopcion.views.SolicitudAdopcion.objects.filter") as request_filter,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
            patch("mod_adopcion.views.render", return_value=HttpResponse("detail")) as render_mock,
        ):
            rescue_query.return_value.filter.return_value.first.return_value = rescate
            vaccine_query.return_value.filter.return_value = vacunas_animal
            personal_filter.return_value.exists.return_value = True
            request_filter.return_value.first.return_value = None
            state_filter.return_value.order_by.return_value.first.return_value = (
                SimpleNamespace(pk=animal.id_estado)
            )

            response = views.detalle_animal(request, id_animal=7)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(render_mock.call_args.args[2]["puede_editar"])
        self.assertEqual(render_mock.call_args.args[2]["rescate"], rescate)
        self.assertEqual(
            render_mock.call_args.args[2]["personal_nombre"],
            "Ana María Pérez López",
        )
        self.assertEqual(
            render_mock.call_args.args[2]["vacunas_animal"],
            vacunas_animal,
        )
        rescue_query.assert_called_once_with(
            "id_estado",
            "rut_personal",
            "rut_personal__id_usuario",
        )
        rescue_query.return_value.filter.assert_called_once_with(pk=14)
        vaccine_query.assert_called_once_with("id_vacuna")
        vaccine_query.return_value.filter.assert_called_once_with(
            id_animal=animal
        )

    def test_animal_detail_does_not_enable_editing_for_public_user(self):
        animal = SimpleNamespace(pk=7, id_estado=21, id_rescate=14)
        request = RequestFactory().get("/adopcion/animales/7/")
        request.session = {"refugio_usuario": {"id": "public-uuid"}}

        with (
            patch("mod_adopcion.views.get_object_or_404", return_value=animal),
            patch("mod_adopcion.views.Rescate.objects.select_related") as rescue_query,
            patch(
                "mod_adopcion.views.VacunaAnimal.objects.select_related"
            ) as vaccine_query,
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch("mod_adopcion.views.SolicitudAdopcion.objects.filter") as request_filter,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
            patch("mod_adopcion.views.render", return_value=HttpResponse("detail")) as render_mock,
        ):
            rescue_query.return_value.filter.return_value.first.return_value = None
            vaccine_query.return_value.filter.return_value = []
            personal_filter.return_value.exists.return_value = False
            request_filter.return_value.first.return_value = None
            state_filter.return_value.order_by.return_value.first.return_value = (
                SimpleNamespace(pk=animal.id_estado)
            )

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
            {"animal": animal, "puede_solicitar_adopcion": True},
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
            {
                "animal": animal,
                "solicitud_existente": solicitud,
                "puede_solicitar_adopcion": True,
            },
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
            patch("mod_adopcion.views.Animal.objects.filter") as animal_query,
            patch("mod_adopcion.views.Animal.objects.order_by") as species_query,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
        ):
            state_filter.return_value.order_by.return_value.first.return_value = (
                SimpleNamespace(pk=21)
            )
            animal_query.return_value.select_related.return_value.order_by.return_value = [
                animal
            ]
            species_query.return_value.values_list.return_value.distinct.return_value = [
                "perro"
            ]

            response = views.animales_adopcion(request)

        self.assertEqual(response.status_code, 200)
        animal_query.assert_called_once_with(id_estado=21)
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
        animal = SimpleNamespace(pk=7, id_estado=9, save=Mock())
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
            patch("mod_adopcion.views.messages.success") as success_mock,
        ):
            animal_lock.return_value.get.return_value = animal
            filter_mock.return_value.exists.return_value = False
            state = SimpleNamespace(pk=9)
            state_filter.return_value.order_by.return_value.first.return_value = state

            response = solicitar_adopcion(request, animal_id=7)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("mod_adopcion:mis_solicitudes"))
        success_mock.assert_called_once_with(
            request,
            "Tu solicitud de adopción fue enviada. El refugio la revisará.",
        )
        create_mock.assert_called_once_with(
            id_animal=animal,
            id_usuario=usuario,
            motivo="Quiero adoptar",
            observacion="Tengo experiencia",
            id_estado=state,
            fecha_solicitud=views.timezone.localdate(),
        )
        self.assertEqual(animal.id_estado, views.ESTADO_ANIMAL_OCULTO_ID)
        animal.save.assert_called_once_with(update_fields=("id_estado",))
