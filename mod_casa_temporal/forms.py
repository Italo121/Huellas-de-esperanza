from django import forms
from django.db.models import Exists, OuterRef

from mod_refugio.models import Animal

from .models import HogarAnimal


class AnimalDisponibleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, animal):
        return f"{animal.nombre or f'Animal {animal.pk}'} ({animal.especie})"


class RespuestaSolicitudHogarTemporalForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("Aprobada", "Aprobar"),
            ("Rechazada", "Rechazar"),
        )
    )
    respuesta = forms.CharField(
        required=False,
        strip=True,
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "maxlength": 255,
                "placeholder": "Respuesta para la persona solicitante (opcional)",
            }
        ),
    )


class GestionHogaresTemporalesForm(forms.Form):
    id_animal = AnimalDisponibleChoiceField(
        label="Animal",
        queryset=Animal.objects.none(),
        empty_label="Selecciona un animal",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        asignacion_activa = HogarAnimal.objects.filter(
            id_animal_id=OuterRef("pk"),
            fecha_salida__isnull=True,
        )
        self.fields["id_animal"].queryset = (
            Animal.objects.filter(fecha_salida__isnull=True)
            .annotate(tiene_asignacion_activa=Exists(asignacion_activa))
            .filter(tiene_asignacion_activa=False)
            .order_by("nombre", "id_animal")
        )


class SolicitudHogarTemporalForm(forms.Form):
    poblacion = forms.CharField(
        label="Localidad",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    calle = forms.CharField(
        label="Calle",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    num_casa = forms.IntegerField(
        label="Número de casa",
        min_value=0,
        max_value=32767,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    cant_persona = forms.IntegerField(
        label="Cantidad de personas en el hogar",
        min_value=1,
        max_value=32767,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    cant_habitacion = forms.IntegerField(
        label="Cantidad de habitaciones",
        min_value=1,
        max_value=32767,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    patio = forms.BooleanField(
        label="La vivienda cuenta con patio",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    metro_c = forms.IntegerField(
        label="Superficie disponible (m²)",
        min_value=1,
        max_value=32767,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    evidencia = forms.CharField(
        label="Evidencia del espacio (enlace o descripción)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    observacion_casa = forms.CharField(
        label="Observaciones sobre la vivienda",
        required=False,
        max_length=255,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
    motivo = forms.CharField(
        label="Motivo de la postulación",
        max_length=255,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
