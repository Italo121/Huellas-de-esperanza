from io import BytesIO
from datetime import date
from contextlib import nullcontext
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from httpx import ReadTimeout

from . import views
from .models import (
    Animal,
    EvaluacionAnimal,
    Estado,
    Personal,
    Tratamiento,
    Vacuna,
    VacunaAnimal,
    Veterinario,
)


class ModelosSaludAnimalTests(SimpleTestCase):
    def test_health_models_map_to_existing_unmanaged_tables(self):
        expected_tables = {
            Veterinario: "veterinario",
            EvaluacionAnimal: "evaluacion_animal",
            Vacuna: "vacuna",
            VacunaAnimal: "vacuna_animal",
            Tratamiento: "tratamiento",
        }

        for model, table_name in expected_tables.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.db_table, table_name)
                self.assertFalse(model._meta.managed)

    def test_health_relationships_point_to_their_domain_models(self):
        self.assertIs(
            Veterinario._meta.get_field("rut_personal").remote_field.model,
            Personal,
        )
        self.assertIs(
            EvaluacionAnimal._meta.get_field("id_animal").remote_field.model,
            Animal,
        )
        self.assertIs(
            EvaluacionAnimal._meta.get_field("rut_personal").remote_field.model,
            Veterinario,
        )
        self.assertIs(
            VacunaAnimal._meta.get_field("id_vacuna").remote_field.model,
            Vacuna,
        )
        self.assertIs(
            Tratamiento._meta.get_field("id_estado").remote_field.model,
            Estado,
        )


class GestionSaludAnimalTests(SimpleTestCase):
    def test_non_personal_account_cannot_open_health_management(self):
        request = RequestFactory().get("/refugio/salud-animal/")
        request.session = {"refugio_usuario": {"id": "public-user"}}

        with (
            patch(
                "mod_refugio.views.Personal.objects.select_related"
            ) as personal_query,
            patch("mod_refugio.views.render", return_value=HttpResponse("denied")) as render_mock,
        ):
            personal_query.return_value.get.side_effect = Personal.DoesNotExist
            response = views.gestion_salud_animal(request)

        self.assertEqual(render_mock.call_args.kwargs["status"], 403)

    @patch("mod_refugio.views.redirect")
    @patch("mod_refugio.views.messages.success")
    @patch("mod_refugio.views.Tratamiento.objects")
    @patch("mod_refugio.views.EvaluacionAnimal.objects")
    @patch("mod_refugio.views.get_object_or_404")
    @patch("mod_refugio.views.Animal.objects")
    @patch("mod_refugio.views.Veterinario.objects.filter")
    @patch("mod_refugio.views.Personal.objects.select_related")
    def test_veterinarian_can_record_an_evaluation(
        self,
        personal_query,
        veterinarian_filter,
        animal_manager,
        get_animal,
        evaluation_manager,
        treatment_manager,
        success_message,
        redirect_mock,
    ):
        personal = SimpleNamespace(pk="12345678-9", rol="veterinario")
        veterinarian = SimpleNamespace(pk=personal.pk)
        animal = SimpleNamespace(pk=4)
        personal_query.return_value.get.return_value = personal
        veterinarian_filter.return_value.first.return_value = veterinarian
        animal_manager.select_related.return_value.order_by.return_value = []
        get_animal.return_value = animal
        evaluation_manager.select_related.return_value.filter.return_value.first.return_value = (
            None
        )
        treatment_manager.select_related.return_value.filter.return_value = []
        redirect_mock.return_value = HttpResponse(status=302)

        request = RequestFactory().post(
            "/refugio/salud-animal/?animal=4",
            data={
                "action": "evaluacion",
                "animal_id": "4",
                "fecha": "2026-10-28",
                "estado_salud": "sano",
                "necesita_tratamiento": "on",
                "observacion": "Evaluación de control",
            },
        )
        request.session = {"refugio_usuario": {"id": "veterinarian-user"}}

        response = views.gestion_salud_animal(request)

        self.assertEqual(response.status_code, 302)
        evaluation_manager.create.assert_called_once_with(
            fecha=date(2026, 10, 28),
            estado_salud="sano",
            necesita_tratamiento=True,
            observacion="Evaluación de control",
            id_animal=animal,
            rut_personal=veterinarian,
        )
        success_message.assert_called_once()

    def test_evaluation_form_rejects_states_not_allowed_by_database(self):
        form = views.EvaluacionAnimalForm(
            data={
                "fecha": "2026-10-28",
                "estado_salud": "estable",
                "necesita_tratamiento": "",
                "observacion": "Control",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("estado_salud", form.errors)

    def test_evaluation_form_exposes_database_health_states(self):
        form = views.EvaluacionAnimalForm()

        self.assertEqual(
            form.fields["estado_salud"].choices,
            [
                ("sano", "Sano"),
                ("en_tratamiento", "En tratamiento"),
                ("grave", "Grave"),
            ],
        )

    @patch("mod_refugio.views.render", return_value=HttpResponse("health"))
    @patch("mod_refugio.views.Tratamiento.objects")
    @patch("mod_refugio.views.EvaluacionAnimal.objects")
    @patch("mod_refugio.views.get_object_or_404")
    @patch("mod_refugio.views.Animal.objects")
    @patch("mod_refugio.views.Veterinario.objects.filter")
    @patch("mod_refugio.views.Personal.objects.select_related")
    def test_treatment_requires_latest_evaluation_to_recommend_it(
        self,
        personal_query,
        veterinarian_filter,
        animal_manager,
        get_animal,
        evaluation_manager,
        treatment_manager,
        render_mock,
    ):
        personal = SimpleNamespace(pk="12345678-9", rol="veterinario")
        veterinarian_filter.return_value.first.return_value = SimpleNamespace(
            pk=personal.pk
        )
        personal_query.return_value.get.return_value = personal
        animal_manager.select_related.return_value.order_by.return_value = []
        get_animal.return_value = SimpleNamespace(pk=4)
        evaluation_manager.select_related.return_value.filter.return_value.first.return_value = (
            SimpleNamespace(necesita_tratamiento=False)
        )
        treatment_manager.select_related.return_value.filter.return_value = []
        request = RequestFactory().post(
            "/refugio/salud-animal/?animal=4",
            data={"action": "tratamiento", "animal_id": "4"},
        )
        request.session = {"refugio_usuario": {"id": "veterinarian-user"}}

        response = views.gestion_salud_animal(request)

        self.assertEqual(render_mock.call_args.kwargs["status"], 400)
        context = render_mock.call_args.args[2]
        self.assertIn("evaluación más reciente", context["error"])
        treatment_manager.create.assert_not_called()
        self.assertFalse(context["puede_registrar_tratamiento"])

    @patch("mod_refugio.views.redirect")
    @patch("mod_refugio.views.messages.success")
    @patch("mod_refugio.views.TratamientoAnimalForm")
    @patch("mod_refugio.views.Tratamiento.objects")
    @patch("mod_refugio.views.EvaluacionAnimal.objects")
    @patch("mod_refugio.views.get_object_or_404")
    @patch("mod_refugio.views.Animal.objects")
    @patch("mod_refugio.views.Veterinario.objects.filter")
    @patch("mod_refugio.views.Personal.objects.select_related")
    def test_veterinarian_can_record_treatment_after_recommended_evaluation(
        self,
        personal_query,
        veterinarian_filter,
        animal_manager,
        get_animal,
        evaluation_manager,
        treatment_manager,
        treatment_form_class,
        success_message,
        redirect_mock,
    ):
        personal = SimpleNamespace(pk="12345678-9", rol="veterinario")
        veterinarian = SimpleNamespace(pk=personal.pk)
        animal = SimpleNamespace(pk=4)
        state = SimpleNamespace(pk=8)
        personal_query.return_value.get.return_value = personal
        veterinarian_filter.return_value.first.return_value = veterinarian
        animal_manager.select_related.return_value.order_by.return_value = []
        get_animal.return_value = animal
        evaluation_manager.select_related.return_value.filter.return_value.first.return_value = (
            SimpleNamespace(necesita_tratamiento=True)
        )
        treatment_manager.select_related.return_value.filter.return_value = []
        form = treatment_form_class.return_value
        form.is_valid.return_value = True
        form.cleaned_data = {
            "fecha_inicio": date(2026, 10, 28),
            "fecha_termino": None,
            "tipo_tratamiento": "control",
            "detalle": "Limpieza diaria",
            "observacion": "",
            "diagnostico": "Herida superficial",
            "costo": 15000,
            "id_estado": state,
        }
        redirect_mock.return_value = HttpResponse(status=302)
        request = RequestFactory().post(
            "/refugio/salud-animal/?animal=4",
            data={"action": "tratamiento", "animal_id": "4"},
        )
        request.session = {"refugio_usuario": {"id": "veterinarian-user"}}

        response = views.gestion_salud_animal(request)

        self.assertEqual(response.status_code, 302)
        treatment_manager.create.assert_called_once_with(
            fecha_inicio=date(2026, 10, 28),
            fecha_termino=None,
            tipo_tratamiento="control",
            detalle="Limpieza diaria",
            observacion=None,
            diagnostico="Herida superficial",
            costo=15000,
            id_estado=state,
            rut_personal=veterinarian,
            id_animal=animal,
        )
        success_message.assert_called_once()

    def test_treatment_form_rejects_types_not_allowed_by_database(self):
        form = views.TratamientoAnimalForm(
            data={
                "fecha_inicio": "2026-10-28",
                "fecha_termino": "",
                "tipo_tratamiento": "test",
                "detalle": "Detalle",
                "observacion": "",
                "diagnostico": "Diagnóstico",
                "costo": "25000",
                "id_estado": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("tipo_tratamiento", form.errors)

    def test_treatment_form_exposes_database_types(self):
        form = views.TratamientoAnimalForm()

        self.assertEqual(
            form.fields["tipo_tratamiento"].choices,
            [
                ("vacuna", "Vacuna"),
                ("cirugia", "Cirugía"),
                ("control", "Control"),
                ("desparasitacion", "Desparasitación"),
                ("otro", "Otro"),
            ],
        )


class GestionVacunasTests(SimpleTestCase):
    @patch("mod_refugio.views.redirect")
    @patch("mod_refugio.views.messages.success")
    @patch("mod_refugio.views.VacunaAnimal.objects")
    @patch("mod_refugio.views.VacunaAnimalForm")
    @patch("mod_refugio.views.get_object_or_404")
    @patch("mod_refugio.views.Animal.objects")
    @patch("mod_refugio.views.Veterinario.objects.filter")
    @patch("mod_refugio.views.Personal.objects.get")
    def test_veterinarian_can_register_vaccine_for_animal(
        self,
        personal_get,
        veterinarian_filter,
        animal_manager,
        get_animal,
        form_class,
        vaccine_manager,
        success_message,
        redirect_mock,
    ):
        personal = SimpleNamespace(pk="12345678-9", rol="veterinario")
        veterinarian_filter.return_value.first.return_value = SimpleNamespace(
            pk=personal.pk
        )
        vaccine = SimpleNamespace(pk=2)
        animal = SimpleNamespace(pk=4)
        personal_get.return_value = personal
        animal_manager.select_related.return_value.order_by.return_value = []
        get_animal.return_value = animal
        vaccine_manager.select_related.return_value.filter.return_value = []
        form = form_class.return_value
        form.is_valid.return_value = True
        form.cleaned_data = {
            "id_vacuna": vaccine,
            "fecha_aplicacion": date(2026, 10, 28),
            "fecha_prox_dosis": None,
            "aplicada": True,
            "observacion": "Aplicada sin reacción.",
        }
        redirect_mock.return_value = HttpResponse(status=302)
        request = RequestFactory().post(
            "/refugio/vacunas/?animal=4",
            data={"animal_id": "4"},
        )
        request.session = {"refugio_usuario": {"id": "veterinarian-user"}}

        response = views.gestion_vacunas(request)

        self.assertEqual(response.status_code, 302)
        vaccine_manager.create.assert_called_once_with(
            fecha_aplicacion=date(2026, 10, 28),
            fecha_prox_dosis=None,
            aplicada=True,
            observacion="Aplicada sin reacción.",
            id_animal=animal,
            id_vacuna=vaccine,
        )
        success_message.assert_called_once()

    def test_vaccine_form_allows_no_next_dose(self):
        form = views.VacunaAnimalForm()

        self.assertFalse(form.fields["fecha_prox_dosis"].required)

    def test_vaccine_form_rejects_next_dose_before_application(self):
        form = views.VacunaAnimalForm(
            data={
                "id_vacuna": "",
                "fecha_aplicacion": "2026-10-28",
                "fecha_prox_dosis": "2026-10-27",
                "aplicada": "on",
                "observacion": "Control",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("fecha_prox_dosis", form.errors)


class RegistroUsuarioTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().post(
            "/refugio/registro/",
            data={
                "p_nombre": "Ana",
                "s_nombre": "María",
                "ap_paterno": "Prueba",
                "ap_materno": "Apellido",
                "correo": "ana@example.com",
                "genero": "femenino",
                "fecha_nacimiento": "1990-01-02",
                "telefono": "+56912345678",
                "password": "password123",
                "password_confirmation": "password123",
            },
        )

    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    def test_existing_local_email_does_not_create_supabase_account(
        self,
        filter_mock,
        supabase_mock,
    ):
        filter_mock.return_value.first.return_value = SimpleNamespace(
            supabase_uid="existing-uid"
        )

        response = views.registro_usuario(self.request)

        self.assertEqual(response.status_code, 400)
        supabase_mock.auth.sign_up.assert_not_called()
        self.assertIn(b"correo", response.content.lower())

    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    def test_supabase_account_error_is_reported_without_local_insert(
        self,
        filter_mock,
        supabase_mock,
    ):
        filter_mock.return_value.first.return_value = None
        error = Exception("User already registered")
        error.code = "user_already_exists"
        supabase_mock.auth.sign_up.side_effect = error

        response = views.registro_usuario(self.request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"ya existe una cuenta con este correo", response.content.lower())

    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    def test_supabase_timeout_does_not_create_local_duplicate(
        self,
        filter_mock,
        supabase_mock,
    ):
        filter_mock.return_value.first.return_value = None
        supabase_mock.auth.sign_up.side_effect = ReadTimeout("request timed out")

        response = views.registro_usuario(self.request)

        self.assertEqual(response.status_code, 504)
        self.assertIn(b"es posible que tu cuenta se haya creado", response.content.lower())
        filter_mock.assert_called_once_with(correo__iexact="ana@example.com")

    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    def test_email_rate_limit_has_specific_response(
        self,
        filter_mock,
        supabase_mock,
    ):
        filter_mock.return_value.first.return_value = None
        error = Exception("email rate limit exceeded")
        error.status = 429
        error.code = "email_rate_limit_exceeded"
        supabase_mock.auth.sign_up.side_effect = error

        response = views.registro_usuario(self.request)

        self.assertEqual(response.status_code, 429)
        self.assertIn("no podemos enviar más correos".encode(), response.content.lower())

    @patch("mod_refugio.views.messages.success")
    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    def test_sends_form_fields_as_auth_metadata_and_checks_trigger_profile(
        self,
        filter_mock,
        supabase_mock,
        success_mock,
    ):
        auth_user_id = "123e4567-e89b-12d3-a456-426614174000"
        local_profile = SimpleNamespace(
            p_nombre="Ana",
            s_nombre="María",
            ap_paterno="Prueba",
            ap_materno="Apellido",
            correo="ana@example.com",
            genero="femenino",
            fecha_nacimiento=date(1990, 1, 2),
        )
        filter_mock.return_value.first.side_effect = [None, local_profile]
        supabase_mock.auth.sign_up.return_value = SimpleNamespace(
            user=SimpleNamespace(id=auth_user_id)
        )

        response = views.registro_usuario(self.request)

        self.assertEqual(response.status_code, 302)
        supabase_mock.auth.sign_up.assert_called_once_with(
            {
                "email": "ana@example.com",
                "password": "password123",
                "options": {
                    "data": {
                        "p_nombre": "Ana",
                        "s_nombre": "María",
                        "ap_paterno": "Prueba",
                        "ap_materno": "Apellido",
                        "genero": "femenino",
                        "fecha_nacimiento": "1990-01-02",
                        "telefono": "+56912345678",
                    }
                },
            }
        )
        filter_mock.assert_any_call(supabase_uid=auth_user_id)
        success_mock.assert_called_once()

    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    def test_missing_trigger_profile_is_not_reported_as_success(
        self,
        filter_mock,
        supabase_mock,
    ):
        filter_mock.return_value.first.side_effect = [None, None]
        supabase_mock.auth.sign_up.return_value = SimpleNamespace(
            user=SimpleNamespace(id="123e4567-e89b-12d3-a456-426614174000")
        )

        response = views.registro_usuario(self.request)

        self.assertEqual(response.status_code, 502)
        self.assertIn(
            "no pudimos guardar correctamente tus datos",
            response.content.decode().lower(),
        )


class LoginUsuarioTests(SimpleTestCase):
    @patch("mod_refugio.views.supabase")
    @patch("mod_refugio.views.Usuario.objects.filter")
    @patch("mod_refugio.views.Usuario.objects.select_related")
    def test_login_links_pending_local_user_by_authenticated_email(
        self,
        select_related_mock,
        filter_mock,
        supabase_mock,
    ):
        request = RequestFactory().post(
            "/refugio/login/",
            data={"email": "ana@example.com", "password": "password123"},
        )
        request.session = {}
        auth_user_id = "123e4567-e89b-12d3-a456-426614174000"
        supabase_mock.auth.sign_in_with_password.return_value = SimpleNamespace(
            user=SimpleNamespace(id=auth_user_id),
            session=SimpleNamespace(access_token="access-token"),
        )
        select_related_mock.return_value.get.side_effect = [
            views.Usuario.DoesNotExist,
            SimpleNamespace(
                pk=1,
                supabase_uid=auth_user_id,
                p_nombre="Ana",
                s_nombre="",
                ap_paterno="Prueba",
                ap_materno="",
                correo="ana@example.com",
                personal=None,
            ),
        ]
        pending_user = SimpleNamespace(
            pk=1,
            supabase_uid=None,
            save=MagicMock(),
        )
        filter_mock.return_value.first.return_value = pending_user

        response = views.login_usuario(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(pending_user.supabase_uid, auth_user_id)
        self.assertEqual(request.session["refugio_usuario"]["id"], auth_user_id)
        self.assertEqual(
            request.session["supabase_access_token"],
            "access-token",
        )


class RegistroAnimalTests(SimpleTestCase):
    def setUp(self):
        atomic_patch = patch(
            "mod_refugio.views.transaction.atomic",
            return_value=nullcontext(),
        )
        atomic_patch.start()
        self.addCleanup(atomic_patch.stop)

    def test_form_context_exposes_rescue_fields_used_by_template(self):
        context = views._registro_animal_context(
            views.RegistroAnimalForm()
        )

        self.assertIn("rescue_fields", context)
        self.assertEqual(
            [field.name for field in context["rescue_fields"]],
            [
                "fecha_rescate",
                "descripcion_rescate",
                "condicion_inicial",
                "observacion_rescate",
                "estado_rescate",
            ],
        )

    def test_state_selectors_are_filtered_by_entity_type(self):
        animal_query_params = (
            views.RegistroAnimalForm.base_fields["estado_animal"]
            .queryset.query.sql_with_params()[1]
        )
        rescue_query_params = (
            views.RegistroAnimalForm.base_fields["estado_rescate"]
            .queryset.query.sql_with_params()[1]
        )

        self.assertIn("Animal", animal_query_params)
        self.assertNotIn("Rescate", animal_query_params)
        self.assertIn("Rescate", rescue_query_params)
        self.assertNotIn("Animal", rescue_query_params)

    def test_image_field_accepts_jpeg_png_and_webp_only(self):
        image_field = views.RegistroAnimalForm.base_fields["foto"]
        valid_png = self._png_upload("animal.png")
        cleaned_image = image_field.clean(valid_png)
        self.assertEqual(cleaned_image.image.format, "PNG")

        invalid_file = SimpleUploadedFile(
            "animal.txt",
            b"not an image",
            content_type="text/plain",
        )
        with self.assertRaises(ValidationError):
            image_field.clean(invalid_file)

    @staticmethod
    def _png_upload(name):
        from PIL import Image

        image_bytes = BytesIO()
        Image.new("RGB", (1, 1), color="green").save(image_bytes, format="PNG")
        return SimpleUploadedFile(
            name,
            image_bytes.getvalue(),
            content_type="image/png",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        request = RequestFactory().get("/refugio/animales/registrar/")
        request.session = {}

        with patch("mod_refugio.views.messages.info"):
            response = views.registro_animal(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/refugio/login/")

    @patch("mod_refugio.views.Personal.objects.get")
    def test_general_user_is_not_allowed_to_register_animals(self, personal_get):
        request = RequestFactory().get("/refugio/animales/registrar/")
        request.session = {
            "refugio_usuario": {"id": "user-uuid", "rol": None}
        }
        personal_get.side_effect = views.Personal.DoesNotExist

        response = views.registro_animal(request)

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"integrantes del personal", response.content.lower())

    @patch("mod_refugio.views.messages.success")
    @patch("mod_refugio.views.Animal.objects.create")
    @patch("mod_refugio.views.Rescate.objects.create")
    @patch("mod_refugio.views.RegistroAnimalForm")
    @patch("mod_refugio.views.Personal.objects.get")
    @patch("mod_refugio.views.supabase_storage")
    def test_personal_creates_rescue_and_animal_together(
        self,
        storage_mock,
        personal_get,
        form_class,
        rescue_create,
        animal_create,
        success_message,
    ):
        personal = SimpleNamespace(rut_personal="12345678-9")
        rescue_state = SimpleNamespace(pk=11)
        animal_state = SimpleNamespace(pk=12)
        breed = SimpleNamespace(pk=13)
        rescue = SimpleNamespace(pk=14)
        personal_get.return_value = personal
        form = form_class.return_value
        form.is_valid.return_value = True
        form.cleaned_data = {
            "nombre": "Luna",
            "edad_aprox": 2,
            "sexo": "hembra",
            "peso": 12.5,
            "descripcion": "Rescatada en la ciudad.",
            "lugar_rescate": "Santiago",
            "condicion": "sano",
            "especie": "perro",
            "microchip": True,
            "foto": SimpleNamespace(
                image=SimpleNamespace(format="PNG"),
                content_type="image/png",
                file=BytesIO(b"png"),
                seek=MagicMock(),
                read=MagicMock(return_value=b"png"),
            ),
            "fecha_ingreso": date(2026, 10, 28),
            "comportamiento": "Amigable",
            "raza": breed,
            "estado_animal": animal_state,
            "fecha_rescate": date(2026, 10, 27),
            "descripcion_rescate": "Encontrada en la calle.",
            "condicion_inicial": "en_tratamiento",
            "observacion_rescate": "",
            "estado_rescate": rescue_state,
        }
        rescue_create.return_value = rescue
        bucket = storage_mock.storage.from_.return_value
        bucket.get_public_url.return_value = (
            "https://project.supabase.co/storage/v1/object/public/"
            "animales/user-uuid/image.png"
        )
        request = RequestFactory().post(
            "/refugio/animales/registrar/",
            data={},
        )
        request.session = {
            "refugio_usuario": {"id": "user-uuid", "rol": "cuidador"}
        }

        response = views.registro_animal(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/refugio/")
        bucket.upload.assert_called_once()
        image_path = bucket.upload.call_args.args[0]
        self.assertRegex(image_path, r"^user-uuid/[0-9a-f]{32}\.png$")
        self.assertEqual(
            bucket.upload.call_args.args[2],
            {"content-type": "image/png", "upsert": "false"},
        )
        self.assertEqual(bucket.upload.call_args.args[1], b"png")
        rescue_create.assert_called_once_with(
            fecha_rescate=date(2026, 10, 27),
            lugar_rescate="Santiago",
            descripcion="Encontrada en la calle.",
            condicion_inicial="en_tratamiento",
            observacion=None,
            id_estado=rescue_state,
            rut_personal=personal,
        )
        animal_create.assert_called_once_with(
            nombre="Luna",
            edad_aprox=2,
            sexo="hembra",
            peso=12.5,
            descripcion="Rescatada en la ciudad.",
            lugar_rescate="Santiago",
            condicion="sano",
            especie="perro",
            microchip=True,
            foto_url=bucket.get_public_url.return_value,
            fecha_ingreso=date(2026, 10, 28),
            fecha_salida=None,
            comportamiento="Amigable",
            raza=breed,
            id_rescate=14,
            id_estado=12,
        )
        success_message.assert_called_once()


class FichaAnimalTests(SimpleTestCase):
    @patch("mod_refugio.views.render", return_value=HttpResponse("detail"))
    @patch("mod_refugio.views.Rescate.objects")
    @patch("mod_refugio.views.Estado.objects")
    @patch("mod_refugio.views.get_object_or_404")
    @patch("mod_refugio.views.Personal.objects.filter")
    @patch("mod_refugio.views.VacunaAnimal.objects.select_related")
    def test_detail_view_loads_animal_state_and_rescue_without_writing(
        self,
        vaccine_query,
        personal_filter,
        get_animal,
        state_manager,
        rescue_manager,
        render_mock,
    ):
        animal = SimpleNamespace(
            id_animal=7,
            id_estado=3,
            id_rescate=12,
            raza=SimpleNamespace(nomb_raza="Mestizo"),
        )
        get_animal.return_value = animal
        state_manager.filter.return_value.first.return_value = SimpleNamespace(
            nombre="Disponible"
        )
        personal_filter.return_value.exists.return_value = False
        rescue_manager.select_related.return_value.filter.return_value.first.return_value = (
            None
        )
        vaccines = [SimpleNamespace(id_vacuna=SimpleNamespace(nomb_vacuna="Antirrábica"))]
        vaccine_query.return_value.filter.return_value = vaccines

        request = RequestFactory().get("/refugio/animales/7/")
        request.session = {}
        response = views.ficha_animal(request, animal_id=7)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(render_mock.call_args.args[1], "ficha_animal.html")
        context = render_mock.call_args.args[2]
        self.assertEqual(context["animal"], animal)
        self.assertEqual(context["estado_animal"].nombre, "Disponible")
        self.assertIsNone(context["rescate"])
        self.assertEqual(context["vacunas_animal"], vaccines)
        self.assertFalse(context["puede_editar"])
        get_animal.assert_called_once()
        self.assertEqual(get_animal.call_args.kwargs, {"pk": 7})
        rescue_manager.create.assert_not_called()


class EditarAnimalTests(SimpleTestCase):
    def test_general_user_cannot_access_animal_edit_form(self):
        request = RequestFactory().get("/refugio/animales/7/editar/")
        request.session = {
            "refugio_usuario": {"id": "general-user", "rol": None}
        }

        with patch(
            "mod_refugio.views.Personal.objects.get",
            side_effect=views.Personal.DoesNotExist,
        ):
            response = views.editar_animal(request, animal_id=7)

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"integrantes del personal", response.content.lower())

    @patch("mod_refugio.views.messages.info")
    def test_anonymous_user_is_redirected_to_login(self, _message):
        request = RequestFactory().get("/refugio/animales/7/editar/")
        request.session = {}

        response = views.editar_animal(request, animal_id=7)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/refugio/login/")

    @patch("mod_refugio.views.messages.success")
    @patch("mod_refugio.views.transaction.atomic", return_value=nullcontext())
    @patch("mod_refugio.views.EditarAnimalForm")
    @patch("mod_refugio.views.get_object_or_404")
    @patch("mod_refugio.views.Personal.objects.get")
    def test_personal_can_update_animal_without_changing_rescue(
        self,
        personal_get,
        get_animal,
        form_class,
        _atomic,
        success_message,
    ):
        animal = SimpleNamespace(pk=7, foto_url="existing-photo", save=MagicMock())
        personal_get.return_value = SimpleNamespace(rut_personal="12345678-9")
        get_animal.return_value = animal
        form = form_class.return_value
        form.is_valid.return_value = True
        form.cleaned_data = {"foto": None}
        form.save.return_value = animal
        request = RequestFactory().post(
            "/refugio/animales/7/editar/",
            data={},
        )
        request.session = {
            "refugio_usuario": {"id": "staff-user", "rol": "cuidador"}
        }

        response = views.editar_animal(request, animal_id=7)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/refugio/animales/7/")
        animal.save.assert_called_once()
        self.assertEqual(animal.foto_url, "existing-photo")
        success_message.assert_called_once()
