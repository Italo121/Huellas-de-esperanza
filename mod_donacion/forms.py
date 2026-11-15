from django import forms

from .models import Donacion, Necesidad

CATEGORIAS_DONACION = (
    ("Alimentos y Nutrición", "Alimentos y Nutrición"),
    ("Limpieza e Higiene", "Limpieza e Higiene"),
    ("Confort y Descanso", "Confort y Descanso"),
    ("Salud y Bienestar", "Salud y Bienestar"),
    ("Aportes Económicos", "Aportes Económicos"),
    ("otro", "Otro"),
)


class NecesidadForm(forms.ModelForm):
    tipo_necesidad = forms.ChoiceField(
        choices=CATEGORIAS_DONACION,
        label="Tipo de necesidad",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Necesidad
        fields = ("tipo_necesidad", "descripcion")
        labels = {
            "tipo_necesidad": "Tipo de necesidad",
            "descripcion": "Descripción",
        }
        widgets = {
            "tipo_necesidad": forms.TextInput(
                attrs={"class": "form-control", "maxlength": 255}
            ),
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "maxlength": 255}
            ),
        }


class DonacionForm(forms.ModelForm):
    tipo_donacion = forms.ChoiceField(
        choices=CATEGORIAS_DONACION,
        label="Tipo de donación",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    cantidad = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label="Cantidad",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
        ),
    )

    class Meta:
        model = Donacion
        fields = ("tipo_donacion", "cantidad", "descripcion", "id_necesidad")
        labels = {
            "tipo_donacion": "Tipo de donación",
            "cantidad": "Cantidad",
            "descripcion": "Descripción",
            "id_necesidad": "Necesidad a apoyar",
        }
        widgets = {
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "maxlength": 255}
            ),
            "id_necesidad": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, necesidad=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.necesidad_preseleccionada = necesidad
        self.fields["id_necesidad"].required = False
        self.fields["id_necesidad"].empty_label = "Donación independiente"
        self.fields["id_necesidad"].queryset = Necesidad.objects.filter(
            saciada=False
        ).order_by("fecha", "id_necesidad")
        if necesidad is not None:
            self.fields["id_necesidad"].initial = necesidad.pk
            self.fields["tipo_donacion"].initial = necesidad.tipo_necesidad
            self.fields["tipo_donacion"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        necesidad = cleaned_data.get("id_necesidad")
        if necesidad is not None:
            cleaned_data["tipo_donacion"] = necesidad.tipo_necesidad
        return cleaned_data
