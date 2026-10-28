from django import forms
from django.core.validators import RegexValidator


class RegistroUsuarioForm(forms.Form):
    p_nombre = forms.CharField(
        max_length=50,
        label="Primer nombre",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    s_nombre = forms.CharField(
        max_length=50,
        label="Segundo nombre",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    ap_paterno = forms.CharField(
        max_length=50,
        label="Apellido paterno",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    ap_materno = forms.CharField(
        max_length=50,
        label="Apellido materno",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    correo = forms.EmailField(
        max_length=50,
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    genero = forms.ChoiceField(
        choices=[
            ("femenino", "Femenino"),
            ("masculino", "Masculino"),
            ("otro", "Otro"),
            ("prefiero_no_decir", "Prefiero no decirlo"),
        ],
        label="Género",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fecha_nacimiento = forms.DateField(
        input_formats=["%Y-%m-%d"],
        label="Fecha de nacimiento",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}
        ),
    )
    telefono = forms.CharField(
        max_length=20,
        label="Teléfono",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "type": "tel",
                "autocomplete": "tel",
            }
        ),
        validators=[
            RegexValidator(
                regex=r"^\+?[0-9]{7,20}$",
                message="Ingresa un teléfono válido de hasta 20 dígitos.",
            )
        ],
    )
    password = forms.CharField(
        min_length=8,
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    password_confirmation = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    def clean_correo(self):
        return self.cleaned_data["correo"].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirmation = cleaned_data.get("password_confirmation")
        if password and password_confirmation and password != password_confirmation:
            self.add_error("password_confirmation", "Las contraseñas no coinciden.")
        return cleaned_data
