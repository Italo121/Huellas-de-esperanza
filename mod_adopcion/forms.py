from django import forms

from .models import SolicitudAdopcion


class SolicitudAdopcionForm(forms.Form):
    motivo = forms.CharField(
        max_length=50,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "maxlength": 50,
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
