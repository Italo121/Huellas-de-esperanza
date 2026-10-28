from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from httpx import ReadTimeout

from . import views


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
