import json
import logging
from uuid import uuid4

from httpx import ReadTimeout
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import EditarAnimalForm, RegistroAnimalForm, RegistroUsuarioForm
from .models import Animal, Estado, Personal, Rescate, Usuario
from .supabase_client import supabase, supabase_storage

logger = logging.getLogger(__name__)


def inicio(request):
    animales = (
        Animal.objects.select_related("raza")
        .order_by("id_animal")
    )
    especies = (
        Animal.objects.order_by()
        .values_list("especie", flat=True)
        .distinct()
    )
    return render(
        request,
        "index.html",
        {
            "animales": animales,
            "especies": especies,
        },
    )


def ficha_animal(request, animal_id):
    animal = get_object_or_404(
        Animal.objects.select_related("raza"),
        pk=animal_id,
    )
    estado_animal = Estado.objects.filter(
        pk=animal.id_estado,
        tipo_estado="Animal",
    ).first()
    rescate = (
        Rescate.objects.select_related(
            "id_estado",
            "rut_personal",
            "rut_personal__id_usuario",
        )
        .filter(pk=animal.id_rescate)
        .first()
    )
    personal_nombre = None
    if rescate and rescate.rut_personal.id_usuario:
        usuario = rescate.rut_personal.id_usuario
        personal_nombre = " ".join(
            parte
            for parte in (
                usuario.p_nombre,
                usuario.s_nombre,
                usuario.ap_paterno,
                usuario.ap_materno,
            )
            if parte
        )

    session_user = request.session.get("refugio_usuario", {})
    puede_editar = bool(
        session_user.get("id")
        and Personal.objects.filter(
            id_usuario__supabase_uid=session_user["id"]
        ).exists()
    )

    return render(
        request,
        "ficha_animal.html",
        {
            "animal": animal,
            "estado_animal": estado_animal,
            "rescate": rescate,
            "personal_nombre": personal_nombre,
            "puede_editar": puede_editar,
        },
    )


def editar_animal(request, animal_id):
    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect("login_usuario")

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "editar_animal.html",
            {"error": "No pudimos verificar tu cuenta. Vuelve a iniciar sesión."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            "editar_animal.html",
            {
                "error": (
                    "La edición está disponible únicamente para integrantes "
                    "del personal del refugio."
                )
            },
            status=403,
        )

    animal = get_object_or_404(Animal, pk=animal_id)
    if request.method == "GET":
        form = EditarAnimalForm(instance=animal)
        return render(
            request,
            "editar_animal.html",
            {"animal": animal, "form": form},
        )
    if request.method != "POST":
        return render(
            request,
            "editar_animal.html",
            {
                "animal": animal,
                "form": EditarAnimalForm(instance=animal),
                "error": "Este formulario solo acepta solicitudes POST.",
            },
            status=405,
        )

    form = EditarAnimalForm(request.POST, request.FILES, instance=animal)
    if not form.is_valid():
        return render(
            request,
            "editar_animal.html",
            {"animal": animal, "form": form},
            status=400,
        )

    uploaded_image = form.cleaned_data["foto"]
    uploaded_image_path = None
    bucket = None
    if uploaded_image:
        if supabase_storage is None:
            return render(
                request,
                "editar_animal.html",
                {
                    "animal": animal,
                    "form": form,
                    "error": (
                        "No está disponible el cambio de foto en este momento. "
                        "Inténtalo más tarde."
                    ),
                },
                status=503,
            )

        image_extensions = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
        image_content_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }
        image_format = uploaded_image.image.format
        uploaded_image_path = (
            f"{session_user['id']}/{uuid4().hex}."
            f"{image_extensions[image_format]}"
        )
        bucket = supabase_storage.storage.from_("animales")
        uploaded_image.seek(0)
        try:
            bucket.upload(
                uploaded_image_path,
                uploaded_image.read(),
                {
                    "content-type": image_content_types[image_format],
                    "upsert": "false",
                },
            )
        except Exception:
            logger.exception(
                "Unable to upload replacement image for animal %s",
                animal.pk,
            )
            return render(
                request,
                "editar_animal.html",
                {
                    "animal": animal,
                    "form": form,
                    "error": (
                        "No pudimos subir la nueva foto. Revisa el archivo "
                        "e inténtalo de nuevo."
                    ),
                },
                status=502,
            )

    try:
        with transaction.atomic():
            animal = form.save(commit=False)
            if uploaded_image_path:
                animal.foto_url = bucket.get_public_url(uploaded_image_path)
            animal.save()
    except DatabaseError:
        logger.exception(
            "Unable to update animal %s by personal %s",
            animal.pk,
            personal.rut_personal,
        )
        if uploaded_image_path:
            try:
                bucket.remove([uploaded_image_path])
            except Exception:
                logger.exception(
                    "Unable to remove orphaned replacement image for animal %s",
                    animal.pk,
                )
        return render(
            request,
            "editar_animal.html",
            {
                "animal": animal,
                "form": form,
                "error": "No pudimos guardar los cambios. Revisa los datos e inténtalo de nuevo.",
            },
            status=500,
        )

    messages.success(request, "Los datos del animal se actualizaron correctamente.")
    return redirect("ficha_animal", animal_id=animal.pk)


def _registro_animal_context(form, error=None):
    return {
        "form": form,
        "error": error,
        "animal_fields": [
            form[name]
            for name in (
                "nombre",
                "edad_aprox",
                "sexo",
                "peso",
                "descripcion",
                "lugar_rescate",
                "condicion",
                "especie",
                "microchip",
                "foto",
                "fecha_ingreso",
                "comportamiento",
                "raza",
                "estado_animal",
            )
        ],
        "rescue_fields": [
            form[name]
            for name in (
                "fecha_rescate",
                "descripcion_rescate",
                "condicion_inicial",
                "observacion_rescate",
                "estado_rescate",
            )
        ],
    }


def registro_animal(request):
    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect("login_usuario")

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "registro_animal.html",
            {"error": "No pudimos verificar tu cuenta. Vuelve a iniciar sesión."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            "registro_animal.html",
            {
                "error": (
                    "Esta función está disponible únicamente para integrantes "
                    "del personal del refugio."
                )
            },
            status=403,
        )

    if request.method == "GET":
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(RegistroAnimalForm()),
        )
    if request.method != "POST":
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(
                RegistroAnimalForm(),
                "Este formulario solo acepta solicitudes POST.",
            ),
            status=405,
        )

    form = RegistroAnimalForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(form),
            status=400,
        )

    datos = form.cleaned_data
    foto_url = None
    uploaded_image = datos["foto"]
    uploaded_image_path = None
    if uploaded_image:
        if supabase_storage is None:
            return render(
                request,
                "registro_animal.html",
                _registro_animal_context(
                    form,
                    (
                        "La carga de fotos no está disponible en este momento. "
                        "Inténtalo más tarde."
                    ),
                ),
                status=503,
            )

        image_extensions = {
            "JPEG": "jpg",
            "PNG": "png",
            "WEBP": "webp",
        }
        image_content_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }
        image_format = uploaded_image.image.format
        uploaded_image_path = (
            f"{session_user['id']}/{uuid4().hex}."
            f"{image_extensions[image_format]}"
        )
        uploaded_image.seek(0)
        bucket = supabase_storage.storage.from_("animales")
        try:
            bucket.upload(
                uploaded_image_path,
                uploaded_image.read(),
                {
                    "content-type": image_content_types[image_format],
                    "upsert": "false",
                },
            )
            foto_url = bucket.get_public_url(uploaded_image_path)
        except Exception:
            logger.exception(
                "Unable to upload animal image to storage path %s",
                uploaded_image_path,
            )
            try:
                bucket.remove([uploaded_image_path])
            except Exception:
                logger.exception(
                    "Unable to clean up failed animal image upload at path %s",
                    uploaded_image_path,
                )
            return render(
                request,
                "registro_animal.html",
                _registro_animal_context(
                    form,
                    (
                        "No pudimos subir la foto. Revisa el archivo e "
                        "inténtalo de nuevo."
                    ),
                ),
                status=502,
            )

    try:
        with transaction.atomic():
            rescate = Rescate.objects.create(
                fecha_rescate=datos["fecha_rescate"],
                lugar_rescate=datos["lugar_rescate"],
                descripcion=datos["descripcion_rescate"],
                condicion_inicial=datos["condicion_inicial"],
                observacion=datos["observacion_rescate"] or None,
                id_estado=datos["estado_rescate"],
                rut_personal=personal,
            )
            Animal.objects.create(
                nombre=datos["nombre"] or None,
                edad_aprox=datos["edad_aprox"],
                sexo=datos["sexo"],
                peso=datos["peso"],
                descripcion=datos["descripcion"],
                lugar_rescate=datos["lugar_rescate"],
                condicion=datos["condicion"],
                especie=datos["especie"],
                microchip=datos["microchip"],
                foto_url=foto_url,
                fecha_ingreso=datos["fecha_ingreso"],
                fecha_salida=None,
                comportamiento=datos["comportamiento"],
                raza=datos["raza"],
                id_rescate=rescate.pk,
                id_estado=datos["estado_animal"].pk,
            )
    except DatabaseError:
        logger.exception(
            "Unable to save animal and rescue for personal %s",
            personal.rut_personal,
        )
        if uploaded_image_path:
            try:
                supabase_storage.storage.from_("animales").remove(
                    [uploaded_image_path]
                )
            except Exception:
                logger.exception(
                    "Unable to remove orphaned animal image at path %s",
                    uploaded_image_path,
                )
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(
                form,
                (
                    "No pudimos guardar el animal y su rescate. "
                    "Revisa los datos e inténtalo de nuevo."
                ),
            ),
            status=500,
        )

    messages.success(request, "El animal y su rescate se registraron correctamente.")
    return redirect("inicio_refugio")


def login_usuario(request):
    if request.method == "GET":
        return render(request, "login.html")
    if request.method != "POST":
        return render(
            request,
            "login.html",
            {"error": "Este formulario solo acepta solicitudes POST."},
            status=405,
        )

    email = request.POST.get("email", "").strip().lower()
    password = request.POST.get("password", "")
    if not email or not password:
        return render(
            request,
            "login.html",
            {"error": "Ingresa tu correo electrónico y contraseña.", "email": email},
            status=400,
        )
    if supabase is None:
        return render(
            request,
            "login.html",
            {
                "error": (
                    "El inicio de sesión no está disponible en este momento. "
                    "Inténtalo más tarde."
                )
            },
            status=503,
        )

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception:
        return render(
            request,
            "login.html",
            {
                "error": (
                    "No pudimos iniciar sesión. Revisa tu correo y contraseña "
                    "e inténtalo de nuevo."
                ),
                "email": email,
            },
            status=401,
        )

    try:
        usuario = Usuario.objects.select_related("personal").get(
            supabase_uid=auth_response.user.id
        )
    except Usuario.DoesNotExist:
        usuario = Usuario.objects.filter(
            correo__iexact=email,
            supabase_uid__isnull=True,
        ).first()
        if usuario is None:
            return render(
                request,
                "login.html",
                {
                    "error": (
                        "No encontramos los datos de tu cuenta. "
                        "Contacta al equipo del refugio."
                    ),
                    "email": email,
                },
                status=404,
            )

        usuario.supabase_uid = auth_response.user.id
        usuario.save(update_fields=["supabase_uid"])
        usuario = Usuario.objects.select_related("personal").get(
            pk=usuario.pk
        )

    try:
        personal = usuario.personal
    except Personal.DoesNotExist:
        personal = None

    nombre = " ".join(
        parte
        for parte in (
            usuario.p_nombre,
            usuario.s_nombre,
            usuario.ap_paterno,
            usuario.ap_materno,
        )
        if parte
    )
    request.session["refugio_usuario"] = {
        "id": str(usuario.supabase_uid),
        "nombre": nombre,
        "correo": usuario.correo,
        "rol": personal.rol if personal else None,
    }
    request.session["supabase_access_token"] = auth_response.session.access_token
    return redirect("inicio_refugio")


def registro_usuario(request):
    if request.method == "GET":
        return render(request, "registro.html", {"form": RegistroUsuarioForm()})
    if request.method != "POST":
        return render(
            request,
            "registro.html",
            {"form": RegistroUsuarioForm(), "error": "Método no permitido."},
            status=405,
        )

    form = RegistroUsuarioForm(request.POST)
    if not form.is_valid():
        return render(request, "registro.html", {"form": form}, status=400)
    if supabase is None:
        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "El registro no está disponible en este momento. "
                    "Inténtalo más tarde."
                ),
            },
            status=503,
        )

    datos = form.cleaned_data
    correo = datos["correo"]
    existing_user = Usuario.objects.filter(correo__iexact=correo).first()
    if existing_user:
        if existing_user.supabase_uid is None:
            form.add_error(
                "correo",
                (
                    "Ya comenzaste el registro con este correo. Si confirmaste "
                    "tu dirección, intenta iniciar sesión. Si no, revisa tu correo."
                ),
            )
        else:
            form.add_error(
                "correo",
                "Ya existe una cuenta con este correo. Inicia sesión o usa otro.",
            )
        return render(request, "registro.html", {"form": form}, status=400)

    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": correo,
                "password": datos["password"],
                "options": {
                    "data": {
                        "p_nombre": datos["p_nombre"],
                        "s_nombre": datos["s_nombre"],
                        "ap_paterno": datos["ap_paterno"],
                        "ap_materno": datos["ap_materno"],
                        "genero": datos["genero"],
                        "fecha_nacimiento": datos["fecha_nacimiento"].isoformat(),
                        "telefono": datos["telefono"] or None,
                    }
                },
            }
        )
    except Exception as error:
        error_code = getattr(error, "code", None)
        error_status = getattr(error, "status", None)
        logger.warning(
            "Supabase sign-up failed (type=%s, status=%s, code=%s)",
            type(error).__name__,
            error_status,
            error_code,
        )
        if error_code in {"user_already_exists", "email_exists"}:
            form.add_error(
                "correo",
                (
                    "Ya existe una cuenta con este correo. "
                    "Inicia sesión o usa otro."
                ),
            )
            return render(request, "registro.html", {"form": form}, status=400)

        if error_status == 429:
            return render(
                request,
                "registro.html",
                {
                    "form": form,
                    "error": (
                        "Por el momento no podemos enviar más correos de registro. "
                        "Inténtalo más tarde."
                    ),
                },
                status=429,
            )

        if isinstance(error, ReadTimeout):
            return render(
                request,
                "registro.html",
                {
                    "form": form,
                    "error": (
                        "No pudimos confirmar tu registro. Es posible que tu "
                        "cuenta se haya creado. Revisa tu correo o intenta "
                        "iniciar sesión antes de registrarte otra vez."
                    ),
                },
                status=504,
            )

        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "No pudimos crear tu cuenta. Revisa los datos e inténtalo "
                    "de nuevo."
                ),
            },
            status=400,
        )

    if auth_response.user is None:
        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "No pudimos confirmar la creación de tu cuenta. "
                    "Espera un momento antes de volver a intentarlo."
                ),
            },
            status=502,
        )

    usuario = Usuario.objects.filter(
        supabase_uid=auth_response.user.id
    ).first()
    expected_profile = {
        "p_nombre": datos["p_nombre"],
        "s_nombre": datos["s_nombre"],
        "ap_paterno": datos["ap_paterno"],
        "ap_materno": datos["ap_materno"],
        "correo": correo,
        "genero": datos["genero"],
        "fecha_nacimiento": datos["fecha_nacimiento"],
    }
    if (
        usuario is None
        or any(
            getattr(usuario, field) != value
            for field, value in expected_profile.items()
        )
    ):
        logger.error(
            "Supabase account %s was created but its usuario profile is missing "
            "or does not match the submitted registration data.",
            auth_response.user.id,
        )
        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "Tu cuenta se creó, pero no pudimos guardar correctamente "
                    "tus datos. Contacta al equipo del refugio antes de volver "
                    "a registrarte."
                ),
            },
            status=502,
        )

    messages.success(
        request,
        (
            "Tu cuenta fue creada. Si recibes un correo de confirmación, "
            "ábrelo antes de iniciar sesión."
        ),
    )
    return redirect("login_usuario")


@require_POST
def logout_usuario(request):
    request.session.pop("refugio_usuario", None)
    request.session.pop("supabase_access_token", None)
    messages.success(request, "Cerraste sesión correctamente.")
    return redirect("inicio_refugio")


@csrf_exempt
def login_personal(request):
    if request.method != "POST":
        response = JsonResponse(
            {"error": "Este endpoint solo acepta solicitudes POST."},
            status=405,
        )
        response["Allow"] = "POST"
        return response

    try:
        credentials = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo debe contener JSON válido."},
            status=400,
        )

    if not isinstance(credentials, dict):
        return JsonResponse({"error": "El cuerpo JSON debe ser un objeto."}, status=400)

    email = credentials.get("email")
    password = credentials.get("password")
    if (
        not isinstance(email, str)
        or not email
        or not isinstance(password, str)
        or not password
    ):
        return JsonResponse(
            {"error": "Se requieren los campos 'email' y 'password'."},
            status=400,
        )

    if supabase is None:
        return JsonResponse(
            {"error": "La autenticación no está disponible en este momento."},
            status=503,
        )

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception:
        return JsonResponse(
            {"error": "No se pudo autenticar con esas credenciales."},
            status=401,
        )

    try:
        usuario = Usuario.objects.select_related("personal").get(
            supabase_uid=auth_response.user.id
        )
    except Usuario.DoesNotExist:
        return JsonResponse(
            {"error": "El usuario no existe en la base de datos local."},
            status=404,
        )

    try:
        personal = usuario.personal
    except Personal.DoesNotExist:
        personal = None

    nombre = " ".join(
        parte
        for parte in (
            usuario.p_nombre,
            usuario.s_nombre,
            usuario.ap_paterno,
            usuario.ap_materno,
        )
        if parte
    )
    return JsonResponse(
        {
            "access_token": auth_response.session.access_token,
            "usuario": {
                "nombre": nombre,
                "correo": usuario.correo,
            },
            "personal": {
                "rol": personal.rol,
                "rut_personal": personal.rut_personal,
            }
            if personal
            else None,
        }
    )
