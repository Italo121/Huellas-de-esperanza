from unittest.mock import patch

from django.http import HttpResponseForbidden
from django.test import RequestFactory, SimpleTestCase

from . import views


class InventarioDonacionesTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_fecha_invalida_muestra_error_sin_consultar_donaciones(self):
        request = self.factory.get(
            "/estadisticas/donaciones/",
            {"desde": "2026-02-31"},
        )

        with (
            patch(
                "mod_estadistica_reporte.views._administrador_de_sesion",
                return_value=None,
            ),
            patch("mod_estadistica_reporte.views.Donacion.objects") as donaciones,
            patch("mod_estadistica_reporte.views.render") as render,
        ):
            response = views.inventario_donaciones(request)

        self.assertEqual(response, render.return_value)
        render.assert_called_once()
        self.assertEqual(render.call_args.kwargs["status"], 400)
        donaciones.select_related.assert_not_called()

    def test_fecha_inicial_posterior_a_fecha_final_muestra_error(self):
        request = self.factory.get(
            "/estadisticas/donaciones/",
            {"desde": "2026-11-02", "hasta": "2026-11-01"},
        )

        with (
            patch(
                "mod_estadistica_reporte.views._administrador_de_sesion",
                return_value=None,
            ),
            patch("mod_estadistica_reporte.views.Donacion.objects") as donaciones,
            patch("mod_estadistica_reporte.views.render") as render,
        ):
            response = views.inventario_donaciones(request)

        self.assertEqual(response, render.return_value)
        self.assertEqual(render.call_args.kwargs["status"], 400)
        donaciones.select_related.assert_not_called()

    def test_no_administrador_no_puede_ver_el_inventario(self):
        request = self.factory.get("/estadisticas/donaciones/")
        forbidden = HttpResponseForbidden("Solo administrador.")

        with (
            patch(
                "mod_estadistica_reporte.views._administrador_de_sesion",
                return_value=forbidden,
            ),
            patch("mod_estadistica_reporte.views.Donacion.objects") as donaciones,
        ):
            response = views.inventario_donaciones(request)

        self.assertIs(response, forbidden)
        donaciones.select_related.assert_not_called()


class AdministradorAccesoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_usuario_con_rol_administrador_puede_ingresar(self):
        request = self.factory.get("/estadisticas/")
        request.session = {"refugio_usuario": {"id": "admin-user-uuid"}}
        rol_personal = patch(
            "mod_estadistica_reporte.views.Personal.objects.filter"
        )

        with rol_personal as personal_filter:
            personal_filter.return_value.exists.return_value = True
            response = views._administrador_de_sesion(request)

        self.assertIsNone(response)
        personal_filter.assert_called_once_with(
            id_usuario__supabase_uid="admin-user-uuid",
            rol="admin",
        )

    def test_personal_que_no_es_administrador_recibe_prohibido(self):
        request = self.factory.get("/estadisticas/")
        request.session = {"refugio_usuario": {"id": "staff-user-uuid"}}

        with patch(
            "mod_estadistica_reporte.views.Personal.objects.filter"
        ) as personal_filter:
            personal_filter.return_value.exists.return_value = False
            response = views._administrador_de_sesion(request)

        self.assertEqual(response.status_code, 403)
        personal_filter.assert_called_once_with(
            id_usuario__supabase_uid="staff-user-uuid",
            rol="admin",
        )

    def test_usuario_sin_sesion_es_enviado_a_iniciar_sesion(self):
        request = self.factory.get("/estadisticas/")
        request.session = {}

        response = views._administrador_de_sesion(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/refugio/login/", response["Location"])

    def test_no_administrador_no_puede_abrir_ninguna_vista_del_modulo(self):
        forbidden = HttpResponseForbidden("Solo administrador.")
        solicitudes = (
            (views.estadisticas, "/estadisticas/"),
            (views.personal, "/estadisticas/personal/"),
            (views.inventario_donaciones, "/estadisticas/donaciones/"),
        )

        for vista, ruta in solicitudes:
            with self.subTest(ruta=ruta):
                request = self.factory.get(ruta)
                with patch(
                    "mod_estadistica_reporte.views._administrador_de_sesion",
                    return_value=forbidden,
                ):
                    response = vista(request)
                self.assertIs(response, forbidden)
