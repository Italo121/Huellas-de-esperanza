from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import Animal, Estado, Raza, Rescate

MAX_ANIMAL_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_ANIMAL_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_animal_image_size(image):
    if image.size > MAX_ANIMAL_IMAGE_SIZE:
        raise ValidationError("La imagen no puede superar los 5 MB.")


def validate_animal_image_format(image):
    image_format = getattr(getattr(image, "image", None), "format", None)
    if image_format not in ALLOWED_ANIMAL_IMAGE_FORMATS:
        raise ValidationError("La imagen debe ser JPG, PNG o WEBP.")


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


class RegistroAnimalForm(forms.Form):
    nombre = forms.CharField(
        max_length=20,
        label="Nombre",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    edad_aprox = forms.IntegerField(
        min_value=0,
        max_value=32767,
        label="Edad aproximada (años)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    sexo = forms.ChoiceField(
        choices=Animal._meta.get_field("sexo").choices,
        label="Sexo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    peso = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        label="Peso (kg)",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": "0", "step": "0.01"}
        ),
    )
    descripcion = forms.CharField(
        label="Descripción del animal",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    lugar_rescate = forms.CharField(
        max_length=50,
        label="Lugar del rescate",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    condicion = forms.ChoiceField(
        choices=Animal._meta.get_field("condicion").choices,
        label="Condición actual",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    especie = forms.ChoiceField(
        choices=Animal._meta.get_field("especie").choices,
        label="Especie",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    microchip = forms.BooleanField(
        label="Tiene microchip",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    foto = forms.ImageField(
        label="Foto del animal",
        required=False,
        validators=[validate_animal_image_size, validate_animal_image_format],
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": "image/jpeg,image/png,image/webp",
            }
        ),
    )
    fecha_ingreso = forms.DateField(
        label="Fecha de ingreso al refugio",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"}
        ),
    )
    comportamiento = forms.CharField(
        max_length=50,
        label="Comportamiento",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    raza = forms.ModelChoiceField(
        queryset=Raza.objects.order_by("nomb_raza"),
        label="Raza",
        empty_label="Selecciona una raza",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    estado_animal = forms.ModelChoiceField(
        queryset=Estado.objects.filter(tipo_estado="Animal").order_by("nombre"),
        label="Estado del animal",
        empty_label="Selecciona un estado",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fecha_rescate = forms.DateField(
        label="Fecha del rescate",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"}
        ),
    )
    descripcion_rescate = forms.CharField(
        max_length=100,
        label="Descripción del rescate",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    condicion_inicial = forms.ChoiceField(
        choices=Rescate._meta.get_field("condicion_inicial").choices,
        label="Condición al momento del rescate",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    observacion_rescate = forms.CharField(
        max_length=50,
        label="Observación del rescate",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    estado_rescate = forms.ModelChoiceField(
        queryset=Estado.objects.filter(tipo_estado="Rescate").order_by("nombre"),
        label="Estado del rescate",
        empty_label="Selecciona un estado",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        self.fields["fecha_ingreso"].initial = hoy
        self.fields["fecha_rescate"].initial = hoy


class EditarAnimalForm(forms.ModelForm):
    foto = forms.ImageField(
        label="Cambiar foto del animal",
        required=False,
        validators=[validate_animal_image_size, validate_animal_image_format],
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": "image/jpeg,image/png,image/webp",
            }
        ),
    )
    estado_animal = forms.ModelChoiceField(
        queryset=Estado.objects.filter(tipo_estado="Animal").order_by("nombre"),
        label="Estado del animal",
        empty_label="Selecciona un estado",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Animal
        fields = (
            "nombre",
            "edad_aprox",
            "sexo",
            "peso",
            "descripcion",
            "lugar_rescate",
            "condicion",
            "especie",
            "microchip",
            "fecha_ingreso",
            "fecha_salida",
            "comportamiento",
            "raza",
        )
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "edad_aprox": forms.NumberInput(attrs={"class": "form-control"}),
            "sexo": forms.Select(attrs={"class": "form-select"}),
            "peso": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "step": "0.01"}
            ),
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "lugar_rescate": forms.TextInput(attrs={"class": "form-control"}),
            "condicion": forms.Select(attrs={"class": "form-select"}),
            "especie": forms.Select(attrs={"class": "form-select"}),
            "microchip": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "fecha_ingreso": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "fecha_salida": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "comportamiento": forms.TextInput(attrs={"class": "form-control"}),
            "raza": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nombre"].required = False
        self.fields["fecha_salida"].required = False
        self.fields["raza"].queryset = Raza.objects.order_by("nomb_raza")
        if self.instance and self.instance.pk:
            self.fields["estado_animal"].initial = Estado.objects.filter(
                pk=self.instance.id_estado,
                tipo_estado="Animal",
            ).first()

    def save(self, commit=True):
        animal = super().save(commit=False)
        animal.id_estado = self.cleaned_data["estado_animal"].pk
        if commit:
            animal.save()
        return animal
