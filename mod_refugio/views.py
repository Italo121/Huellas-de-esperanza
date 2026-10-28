import json
import logging

from httpx import ReadTimeout
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import RegistroUsuarioForm
from .models import Animal, Personal, Usuario
from .supabase_client import supabase

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
