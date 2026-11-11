from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.forms import Select
from django.test import RequestFactory, SimpleTestCase

from .forms import DonacionForm, NecesidadForm
from . import views


class CategoriaDonacionTests(SimpleTestCase):
    def test_necesidad_y_donacion_usan_las_categorias_definidas(self):
        expected = [
            "Alimentos y Nutrición",
            "Limpieza e Higiene",
            "Confort y Descanso",
            "Salud y Bienestar",
            "Aportes Económicos",
            "otro",
        ]

        self.assertEqual(
            [
                value
                for value, _ in NecesidadForm.base_fields[
                    "tipo_necesidad"
                ].choices
            ],
            expected,
        )
        self.assertEqual(
            [
                value
                for value, _ in DonacionForm.base_fields[
                    "tipo_donacion"
                ].choices
            ],
            expected,
        )
        self.assertIsInstance(
            NecesidadForm.base_fields["tipo_necesidad"].widget,
            Select,
        )
        self.assertIsInstance(
            DonacionForm.base_fields["tipo_donacion"].widget,
            Select,
        )

    def test_tipo_de_donacion_se_toma_de_la_necesidad_seleccionada(self):
        necesidad = SimpleNamespace(pk=12, tipo_necesidad="Salud y Bienestar")
        form = DonacionForm(necesidad=necesidad)

        self.assertTrue(form.fields["tipo_donacion"].disabled)
        form.cleaned_data = {
            "tipo_donacion": "otro",
            "id_necesidad": necesidad,
        }

        self.assertEqual(
            form.clean()["tipo_donacion"],
            necesidad.tipo_necesidad,
        )

    def test_donacion_independiente_permite_elegir_tipo(self):
        form = DonacionForm()

        self.assertFalse(form.fields["tipo_donacion"].disabled)


class GestionDonacionesTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_donaciones_separadas_y_agrupadas_por_necesidad(self):
        necesidad = SimpleNamespace(pk=7)
        donacion_independiente = SimpleNamespace(id_donacion=1)
        donacion_asociada = SimpleNamespace(
            id_donacion=2,
            id_necesidad_id=necesidad.pk,
        )

        independientes = MagicMock()
        independientes.select_related.return_value = independientes
        independientes.order_by.return_value = [donacion_independiente]

        asociadas = MagicMock()
        asociadas.select_related.return_value = asociadas
        asociadas.order_by.return_value = [donacion_asociada]

        request = self.factory.get("/donacion/gestion/")
        with (
            patch(
                "mod_donacion.views._personal_de_sesion",
                return_value=(object(), None),
            ),
            patch(
                "mod_donacion.views.Donacion.objects.filter",
                side_effect=[independientes, asociadas],
            ),
            patch(
                "mod_donacion.views.Necesidad.objects.order_by",
                return_value=[necesidad],
            ),
            patch("mod_donacion.views.render") as render,
        ):
            response = views.gestion_donaciones(request)

        self.assertEqual(response, render.return_value)
        context = render.call_args.args[2]
        self.assertEqual(
            context["donaciones_independientes"],
            [donacion_independiente],
        )
        self.assertEqual(necesidad.donaciones_registradas, [donacion_asociada])

    def test_marcar_necesidad_saciada_registra_estado_y_fecha(self):
        necesidad = SimpleNamespace(pk=9, saciada=False, save=MagicMock())
        request = self.factory.post("/donacion/necesidad/9/saciar/")
        fecha_saciada = date(2026, 11, 8)

        with (
            patch(
                "mod_donacion.views._personal_de_sesion",
                return_value=(object(), None),
            ),
            patch(
                "mod_donacion.views.get_object_or_404",
                return_value=necesidad,
            ),
            patch(
                "mod_donacion.views.timezone.localdate",
                return_value=fecha_saciada,
            ),
            patch("mod_donacion.views.messages.success"),
        ):
            response = views.marcar_necesidad_saciada(request, necesidad.pk)

        self.assertTrue(necesidad.saciada)
        self.assertEqual(necesidad.fecha_cambio, fecha_saciada)
        necesidad.save.assert_called_once_with(
            update_fields=["saciada", "fecha_cambio"]
        )
        self.assertEqual(response.status_code, 302)

    def test_marcar_necesidad_no_permite_metodo_get(self):
        request = self.factory.get("/donacion/necesidad/9/saciar/")

        response = views.marcar_necesidad_saciada(request, 9)

        self.assertEqual(response.status_code, 405)
