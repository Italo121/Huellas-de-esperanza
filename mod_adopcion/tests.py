from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import SimpleTestCase
from django.test import RequestFactory
from django.urls import resolve, reverse

from .forms import RespuestaSolicitudAdopcionForm, SolicitudAdopcionForm
from . import views
from .models import SolicitudAdopcion
from .views import gestion_solicitudes_adopcion, solicitar_adopcion


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

    def test_staff_review_route_resolves_to_existing_view(self):
        path = reverse("mod_adopcion:gestion_solicitudes_adopcion")

        self.assertEqual(path, "/adopcion/gestion-solicitudes/")
        self.assertIs(resolve(path).func, gestion_solicitudes_adopcion)


class SolicitudAdopcionViewTests(SimpleTestCase):
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

    def test_review_approves_only_for_active_staff(self):
        request = RequestFactory().post(
            "/adopcion/gestion-solicitudes/",
            {"solicitud_id": "11", "action": "aprobada", "respuesta": "Aprobada"},
        )
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        personal = SimpleNamespace(pk="12345678-9")
        solicitud = SimpleNamespace(
            id_estado=SimpleNamespace(nombre="Pendiente"),
            save=MagicMock(),
        )
        approved_state = SimpleNamespace(nombre="Aprobada")

        with (
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch("mod_adopcion.views.Estado.objects.filter") as state_filter,
            patch(
                "mod_adopcion.views.SolicitudAdopcion.objects.select_for_update"
            ) as requests_for_update,
            patch("mod_adopcion.views.get_object_or_404", return_value=solicitud),
            patch(
                "mod_adopcion.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_adopcion.views.messages.success"),
        ):
            personal_filter.return_value.order_by.return_value.first.return_value = (
                personal
            )
            state_filter.return_value.order_by.return_value.first.return_value = (
                approved_state
            )
            requests_for_update.return_value = MagicMock()

            response = gestion_solicitudes_adopcion(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(solicitud.id_estado, approved_state)
        self.assertEqual(solicitud.respuesta, "Aprobada")
        self.assertEqual(solicitud.respondida_por, personal)
        solicitud.save.assert_called_once()

    def test_review_denies_non_staff(self):
        request = RequestFactory().get("/adopcion/gestion-solicitudes/")
        request.session = {"refugio_usuario": {"id": "public-uuid"}}

        with (
            patch("mod_adopcion.views.Personal.objects.filter") as personal_filter,
            patch(
                "mod_adopcion.views.render",
                return_value=HttpResponse(status=403),
            ) as render_mock,
        ):
            personal_filter.return_value.order_by.return_value.first.return_value = None
            response = gestion_solicitudes_adopcion(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            personal_filter.call_args.kwargs,
            {
                "id_usuario__supabase_uid": "public-uuid",
                "id_estado__tipo_estado": "Personal",
                "id_estado__nombre": "Activo",
            },
        )
        render_mock.assert_called_once()
