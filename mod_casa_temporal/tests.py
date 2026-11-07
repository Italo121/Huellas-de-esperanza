from django.test import TestCase

# Create your tests here.
from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from mod_refugio.models import Estado, Usuario

from . import views
from .forms import SolicitudHogarTemporalForm
from .models import CasaTemporal, SolicitudHogarTemporal


class SolicitudHogarTemporalSchemaTests(SimpleTestCase):
    def test_status_relations_use_the_same_estado_model_as_the_view(self):
        self.assertIs(
            CasaTemporal._meta.get_field("id_estado").remote_field.model,
            Estado,
        )
        self.assertIs(
            SolicitudHogarTemporal._meta.get_field("id_estado").remote_field.model,
            Estado,
        )

    def test_animal_is_not_part_of_the_application_form_or_table_model(self):
        self.assertNotIn("id_animal", SolicitudHogarTemporalForm().fields)
        self.assertNotIn(
            "id_animal",
            {field.name for field in SolicitudHogarTemporal._meta.get_fields()},
        )

    def test_post_creates_application_without_animal_foreign_key(self):
        request = RequestFactory().post(
            "/casa-temporal/solicitar/",
            {
                "poblacion": "Centro",
                "calle": "Calle Uno",
                "num_casa": "123",
                "cant_persona": "3",
                "cant_habitacion": "2",
                "patio": "on",
                "metro_c": "80",
                "evidencia": "Revisar con el equipo",
                "observacion_casa": "",
                "motivo": "Quiero apoyar al refugio",
                "observacion": "",
            },
        )
        request.session = {"refugio_usuario": {"id": "test-user"}}
        usuario = SimpleNamespace(pk=10, p_nombre="Ana")
        estado_pendiente = Estado(
            id_estado=2,
            tipo_estado="Solicitud",
            nombre="Pendiente",
        )
        casa = SimpleNamespace(pk=20)
        solicitudes = MagicMock()
        solicitudes.select_related.return_value.order_by.return_value.first.return_value = None
        estados = MagicMock()
        estados.order_by.return_value.first.return_value = estado_pendiente

        with (
            patch(
                "mod_casa_temporal.views.Usuario.objects.get",
                return_value=usuario,
            ),
            patch(
                "mod_casa_temporal.views.SolicitudHogarTemporal.objects.filter",
                return_value=solicitudes,
            ),
            patch(
                "mod_casa_temporal.views.Estado.objects.filter",
                return_value=estados,
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.create",
                return_value=casa,
            ) as crear_casa,
            patch(
                "mod_casa_temporal.views.SolicitudHogarTemporal.objects.create",
            ) as crear_solicitud,
            patch(
                "mod_casa_temporal.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_casa_temporal.views.messages.success"),
        ):
            response = views.solicitar_hogar_temporal(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/casa-temporal/solicitar/")
        self.assertIs(crear_casa.call_args.kwargs["id_estado"], estado_pendiente)
        self.assertIs(crear_solicitud.call_args.kwargs["id_estado"], estado_pendiente)
        self.assertNotIn("id_animal", crear_solicitud.call_args.kwargs)


class HogaresDisponiblesTests(SimpleTestCase):
    @patch("mod_casa_temporal.views.render", return_value=HttpResponse("hogares"))
    @patch("mod_casa_temporal.views.CasaTemporal.objects.filter")
    def test_public_listing_only_passes_non_identifying_home_details(
        self,
        filter_hogares,
        render_mock,
    ):
        filter_hogares.return_value.values.return_value.annotate.return_value.order_by.return_value = [
            {
                "id_casa": 12,
                "cant_persona": 3,
                "cant_habitacion": 2,
                "patio": True,
                "metro_c": 80,
                "animales_acogidos": 1,
            }
        ]

        response = views.hogares_disponibles(
            RequestFactory().get("/casa-temporal/hogares/")
        )

        self.assertEqual(response.status_code, 200)
        filter_hogares.assert_called_once_with(
            id_estado__tipo_estado="Solicitud",
            id_estado__nombre="Aprobada",
        )
        context = render_mock.call_args.args[2]
        self.assertEqual(
            context["hogares"],
            [
                {
                    "numero": 1,
                    "cant_persona": 3,
                    "cant_habitacion": 2,
                    "patio": True,
                    "metro_c": 80,
                    "animales_acogidos": 1,
                }
            ],
        )
        self.assertNotIn("id_casa", context["hogares"][0])


class MisHogaresTemporalesTests(SimpleTestCase):
    @patch("mod_casa_temporal.views.render", return_value=HttpResponse("mis hogares"))
    @patch("mod_casa_temporal.views.CasaTemporal.objects.filter")
    @patch(
        "mod_casa_temporal.views.Usuario.objects.get",
        return_value=SimpleNamespace(pk=17),
    )
    def test_owner_listing_filters_by_authenticated_user(
        self,
        usuario_get,
        casas_filter,
        render_mock,
    ):
        request = RequestFactory().get("/casa-temporal/mis-hogares/")
        request.session = {"refugio_usuario": {"id": "owner-uuid"}}
        hogares = casas_filter.return_value
        hogares.select_related.return_value.prefetch_related.return_value.order_by.return_value = [
            SimpleNamespace(pk=4)
        ]

        response = views.mis_hogares_temporales(request)

        self.assertEqual(response.status_code, 200)
        usuario_get.assert_called_once_with(supabase_uid="owner-uuid")
        casas_filter.assert_called_once_with(id_usuario=usuario_get.return_value)
        self.assertEqual(
            render_mock.call_args.args[2]["hogares"],
            [SimpleNamespace(pk=4)],
        )


class GestionHogaresTemporalesTests(SimpleTestCase):
    def _active_home_queryset(self, home):
        queryset = MagicMock()
        queryset.filter.return_value.first.return_value = home
        queryset.select_related.return_value.annotate.return_value.order_by.return_value = queryset
        return queryset

    def _staff_auth_patches(self, personal):
        return (
            patch(
                "mod_casa_temporal.views.Personal.objects.get",
                return_value=personal,
            ),
            patch(
                "mod_casa_temporal.views.Personal.objects.filter"
            ),
        )

    def test_staff_page_shows_active_homes_and_assignment_history_for_selection(self):
        home = SimpleNamespace(pk=23, save=MagicMock())
        assignments = [SimpleNamespace(pk=91)]
        active_home_queryset = self._active_home_queryset(home)
        assignment_queryset = MagicMock()
        assignment_queryset.select_related.return_value.order_by.return_value.filter.return_value = assignments

        with (
            patch(
                "mod_casa_temporal.views.Personal.objects.get",
                return_value=SimpleNamespace(pk="staff-rut"),
            ),
            patch(
                "mod_casa_temporal.views.Personal.objects.filter"
            ) as personal_filter,
            patch(
                "mod_casa_temporal.views.GestionHogaresTemporalesForm",
                return_value=SimpleNamespace(),
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.filter",
                return_value=active_home_queryset,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.all",
                return_value=assignment_queryset,
            ),
            patch(
                "mod_casa_temporal.views.render",
                return_value=HttpResponse("management"),
            ) as render_mock,
        ):
            personal_filter.return_value.exists.return_value = True
            request = RequestFactory().get(
                "/casa-temporal/gestion-hogares/",
                {"casa": "23"},
            )
            request.session = {"refugio_usuario": {"id": "staff-uuid"}}
            response = views.gestion_hogares_temporales(request)

        self.assertEqual(response.status_code, 200)
        context = render_mock.call_args.args[2]
        self.assertIs(context["hogar_seleccionado"], home)
        self.assertIs(context["hogares_activos"], active_home_queryset)
        self.assertEqual(context["asignaciones_hogar"], assignments)

    def test_staff_can_close_assignment_for_selected_home(self):
        request = RequestFactory().post(
            "/casa-temporal/gestion-hogares/",
            {
                "action": "retirar_animal",
                "casa_id": "23",
                "asignacion_id": "91",
            },
        )
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        personal = SimpleNamespace(pk="staff-rut")
        fecha_salida = date(2026, 10, 31)
        assignment = SimpleNamespace(
            fecha_ingreso=date(2026, 10, 20),
            fecha_salida=None,
            save=MagicMock(),
        )
        active_home_queryset = self._active_home_queryset(
            SimpleNamespace(pk=23)
        )
        home_manager = MagicMock()
        home_manager.get.return_value = SimpleNamespace(pk=23)
        assignments_manager = MagicMock()
        assignments_manager.get.return_value = assignment

        with (
            patch(
                "mod_casa_temporal.views.Personal.objects.get",
                return_value=personal,
            ),
            patch(
                "mod_casa_temporal.views.Personal.objects.filter"
            ) as personal_filter,
            patch(
                "mod_casa_temporal.views.GestionHogaresTemporalesForm",
                return_value=SimpleNamespace(),
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.filter",
                return_value=active_home_queryset,
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.select_for_update",
                return_value=home_manager,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.select_for_update",
                return_value=assignments_manager,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.all",
                return_value=MagicMock(),
            ),
            patch(
                "mod_casa_temporal.views.timezone.localdate",
                return_value=fecha_salida,
            ),
            patch(
                "mod_casa_temporal.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_casa_temporal.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.gestion_hogares_temporales(request)

        self.assertEqual(
            response.url,
            "/casa-temporal/gestion-hogares/?casa=23",
        )
        assignments_manager.get.assert_called_once_with(
            pk="91",
            id_casa=home_manager.get.return_value,
            fecha_salida__isnull=True,
        )
        self.assertEqual(assignment.fecha_ingreso, date(2026, 10, 20))
        self.assertEqual(assignment.fecha_salida, fecha_salida)
        assignment.save.assert_called_once_with(update_fields=("fecha_salida",))

    def test_staff_can_assign_animal_to_selected_home(self):
        request = RequestFactory().post(
            "/casa-temporal/gestion-hogares/",
            {
                "action": "asignar_animal",
                "casa_id": "23",
                "id_animal": "41",
            },
        )
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        home = SimpleNamespace(pk=23)
        animal = SimpleNamespace(pk=41)
        form = SimpleNamespace(
            is_valid=MagicMock(return_value=True),
            cleaned_data={"id_animal": animal},
        )
        active_home_queryset = self._active_home_queryset(home)
        home_manager = MagicMock()
        home_manager.get.return_value = home
        animal_manager = MagicMock()
        animal_manager.get.return_value = animal
        assignments = MagicMock()
        assignments.exists.return_value = False

        with (
            patch(
                "mod_casa_temporal.views.Personal.objects.get",
                return_value=SimpleNamespace(pk="staff-rut"),
            ),
            patch(
                "mod_casa_temporal.views.Personal.objects.filter"
            ) as personal_filter,
            patch(
                "mod_casa_temporal.views.GestionHogaresTemporalesForm",
                return_value=form,
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.filter",
                return_value=active_home_queryset,
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.select_for_update",
                return_value=home_manager,
            ),
            patch(
                "mod_casa_temporal.views.Animal.objects.select_for_update",
                return_value=animal_manager,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.filter",
                return_value=assignments,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.create"
            ) as create_assignment,
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.all",
                return_value=MagicMock(),
            ),
            patch(
                "mod_casa_temporal.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_casa_temporal.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.gestion_hogares_temporales(request)

        self.assertEqual(
            response.url,
            "/casa-temporal/gestion-hogares/?casa=23",
        )
        create_assignment.assert_called_once()
        self.assertIs(create_assignment.call_args.kwargs["id_casa"], home)
        self.assertIs(create_assignment.call_args.kwargs["id_animal"], animal)

    def test_home_with_active_animal_cannot_be_deactivated(self):
        request = RequestFactory().post(
            "/casa-temporal/gestion-hogares/",
            {
                "action": "desactivar_hogar",
                "casa_id": "23",
            },
        )
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        home = SimpleNamespace(pk=23, save=MagicMock())
        active_home_queryset = self._active_home_queryset(home)
        home_manager = MagicMock()
        home_manager.get.return_value = home
        assignment_queryset = MagicMock()
        assignment_queryset.exists.return_value = True

        with (
            patch(
                "mod_casa_temporal.views.Personal.objects.get",
                return_value=SimpleNamespace(pk="staff-rut"),
            ),
            patch(
                "mod_casa_temporal.views.Personal.objects.filter"
            ) as personal_filter,
            patch(
                "mod_casa_temporal.views.GestionHogaresTemporalesForm",
                return_value=SimpleNamespace(),
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.filter",
                return_value=active_home_queryset,
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.select_for_update",
                return_value=home_manager,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.filter",
                return_value=assignment_queryset,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.all",
                return_value=MagicMock(),
            ),
            patch("mod_casa_temporal.views.Estado.objects.get_or_create") as get_state,
            patch(
                "mod_casa_temporal.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "mod_casa_temporal.views.render",
                return_value=HttpResponse("management", status=400),
            ) as render_mock,
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.gestion_hogares_temporales(request)

        self.assertEqual(response.status_code, 400)
        get_state.assert_not_called()
        home.save.assert_not_called()
        self.assertIn("tenga animales", render_mock.call_args.args[2]["error"])

    def test_empty_home_can_be_marked_inactive(self):
        request = RequestFactory().post(
            "/casa-temporal/gestion-hogares/",
            {
                "action": "desactivar_hogar",
                "casa_id": "23",
            },
        )
        request.session = {"refugio_usuario": {"id": "staff-uuid"}}
        home = SimpleNamespace(pk=23, save=MagicMock())
        estado_inactivo = SimpleNamespace(
            tipo_estado="Casa temporal",
            nombre="Inactivo",
        )
        active_home_queryset = self._active_home_queryset(home)
        home_manager = MagicMock()
        home_manager.get.return_value = home
        assignment_queryset = MagicMock()
        assignment_queryset.exists.return_value = False

        with (
            patch(
                "mod_casa_temporal.views.Personal.objects.get",
                return_value=SimpleNamespace(pk="staff-rut"),
            ),
            patch(
                "mod_casa_temporal.views.Personal.objects.filter"
            ) as personal_filter,
            patch(
                "mod_casa_temporal.views.GestionHogaresTemporalesForm",
                return_value=SimpleNamespace(),
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.filter",
                return_value=active_home_queryset,
            ),
            patch(
                "mod_casa_temporal.views.CasaTemporal.objects.select_for_update",
                return_value=home_manager,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.filter",
                return_value=assignment_queryset,
            ),
            patch(
                "mod_casa_temporal.views.HogarAnimal.objects.all",
                return_value=MagicMock(),
            ),
            patch(
                "mod_casa_temporal.views.Estado.objects.get_or_create",
                return_value=(estado_inactivo, True),
            ) as get_state,
            patch(
                "mod_casa_temporal.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch("mod_casa_temporal.views.messages.success"),
        ):
            personal_filter.return_value.exists.return_value = True
            response = views.gestion_hogares_temporales(request)

        self.assertEqual(response.url, "/casa-temporal/gestion-hogares/")
        get_state.assert_called_once_with(
            tipo_estado="Casa temporal",
            nombre="Inactivo",
        )
        self.assertIs(home.id_estado, estado_inactivo)
        home.save.assert_called_once_with(update_fields=("id_estado",))
