from django import forms

from .models import Comentario, Publicacion


class PublicacionForm(forms.ModelForm):
    categoria = forms.ChoiceField(
        choices=(
            ("", "Selecciona una categoría"),
            ("adopcion", "Adopción"),
            ("rescate", "Rescate"),
        ),
        error_messages={
            "required": "Selecciona una categoría.",
            "invalid_choice": "Selecciona una categoría válida.",
        },
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def full_clean(self):
        super().full_clean()
        for field_name in self.errors:
            widget = self.fields[field_name].widget
            classes = widget.attrs.get("class", "").split()
            if "is-invalid" not in classes:
                classes.append("is-invalid")
            widget.attrs["class"] = " ".join(classes)
            widget.attrs["aria-invalid"] = "true"
            widget.attrs["aria-describedby"] = f"id_{field_name}_errors"

    class Meta:
        model = Publicacion
        fields = ("categoria", "titulo", "contenido", "ubicacion")
        error_messages = {
            "titulo": {
                "required": "El título es obligatorio.",
                "max_length": "El título no puede superar 30 caracteres.",
            },
            "contenido": {"required": "El mensaje es obligatorio."},
            "ubicacion": {
                "required": "La ubicación es obligatoria.",
                "max_length": "La ubicación no puede superar 150 caracteres.",
            },
        }
        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Título de tu publicación",
                    "maxlength": 30,
                }
            ),
            "contenido": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Comparte una historia, pregunta o novedad...",
                    "rows": 4,
                }
            ),
            "ubicacion": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ciudad, comuna o sector",
                    "maxlength": 150,
                }
            ),
        }


class ComentarioForm(forms.ModelForm):
    contenido = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "placeholder": "Escribe un comentario...",
                "rows": 2,
                "maxlength": 1000,
            }
        ),
    )

    class Meta:
        model = Comentario
        fields = ("contenido",)
