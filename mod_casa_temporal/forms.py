from pathlib import PurePosixPath

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from PIL import Image

from mod_refugio.models import Animal

from .models import HogarAnimal

MAX_EVIDENCE_FILE_SIZE = 5 * 1024 * 1024
EVIDENCE_FILE_TYPES = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
    ".pdf": ("application/pdf", None),
}


def validate_evidence_file(uploaded_file):
    if uploaded_file.size > MAX_EVIDENCE_FILE_SIZE:
        raise ValidationError("Cada archivo debe pesar como máximo 5 MB.")

    extension = PurePosixPath(
        uploaded_file.name.replace("\\", "/")
    ).suffix.lower()
    file_type = EVIDENCE_FILE_TYPES.get(extension)
    if file_type is None:
        raise ValidationError("Solo se permiten archivos JPG, PNG o PDF.")

    uploaded_file.seek(0)
    if extension == ".pdf":
        is_valid = uploaded_file.read(5).startswith(b"%PDF-")
        uploaded_file.seek(0)
        if not is_valid:
            raise ValidationError("El archivo PDF no tiene un formato válido.")
        return

    try:
        with Image.open(uploaded_file) as image:
            image_format = image.format
            image.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        uploaded_file.seek(0)
        raise ValidationError(
            "La imagen debe ser un archivo JPG o PNG válido."
        ) from error
    finally:
        uploaded_file.seek(0)

    if image_format != file_type[1]:
        raise ValidationError(
            "La extensión del archivo no coincide con su formato."
        )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            super().clean(data, initial)
            return []

        files = data if isinstance(data, (list, tuple)) else [data]
        return [
            super(MultipleFileField, self).clean(uploaded_file, initial)
            for uploaded_file in files
        ]


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
        label="Descripción o enlace de la evidencia",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Describe el espacio o pega un enlace.",
            }
        ),
    )
    evidencia_archivos = MultipleFileField(
        label="Adjuntar archivos de evidencia",
        required=False,
        validators=[validate_evidence_file],
        help_text=(
            "JPG, PNG o PDF; máximo 5 MB por archivo. "
            "Puedes seleccionar varios."
        ),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
                "accept": ".jpg,.jpeg,.png,.pdf",
            }
        ),
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

    def clean(self):
        cleaned_data = super().clean()
        if (
            not cleaned_data.get("evidencia")
            and not cleaned_data.get("evidencia_archivos")
        ):
            self.add_error(
                "evidencia",
                "Escribe una descripción o adjunta al menos un archivo.",
            )
        return cleaned_data
