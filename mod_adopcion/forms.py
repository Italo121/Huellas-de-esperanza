from django import forms

from .models import SolicitudAdopcion


class RespuestaDevolucionAdopcionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("aprobada", "Aprobar"),
            ("rechazada", "Rechazar"),
        )
    )


class SolicitudAdopcionForm(forms.Form):
    motivo = forms.CharField(
        min_length=50,
        max_length=200,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "minlength": 50,
                "maxlength": 200,
                "placeholder": "Cuéntanos tus motivos...",
            }
        ),
    )
    observacion = forms.CharField(
        required=False,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Experiencia cuidando animales, espacio disponible, etc.",
            }
        ),
    )


class SolicitudDevolucionAdopcionForm(forms.Form):
    motivo = forms.CharField(
        max_length=50,
        strip=True,
        label="Motivo de la devolución",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "maxlength": 50,
                "placeholder": "Cuéntanos por qué solicitas la devolución",
            }
        ),
    )
    condicion_animal = forms.ChoiceField(
        choices=(
            ("sano", "Sano"),
            ("en_tratamiento", "En tratamiento"),
            ("grave", "Grave"),
        ),
        label="Condición actual del animal",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    observacion = forms.CharField(
        required=False,
        strip=True,
        label="Observaciones",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Información adicional (opcional)",
            }
        ),
    )
    requiere_tratamiento = forms.BooleanField(
        required=False,
        label="El animal requiere tratamiento",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class RespuestaSolicitudAdopcionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            (SolicitudAdopcion.APROBADA, "Aprobar"),
            (SolicitudAdopcion.RECHAZADA, "Rechazar"),
        )
    )
    respuesta = forms.CharField(
        required=False,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Respuesta para la persona solicitante (opcional)",
            }
        ),
    )
